#!/bin/bash -xe
#
# Install and run Skepticoin on Linux aarch64 (ARM64) AWS EC2 instance
#

# install python infrastructure
amazon-linux-extras install python3.8
/usr/bin/python3.8 -m venv ./venv
. ./venv/bin/activate
yum install -y "@Development tools" python3-pip python38-devel blas-devel gcc-gfortran lapack-devel
python -m pip install --upgrade pip
pip install wheel

# upgrade sqlite to 3.34.1 (same as Python 3.8 on Windows)
curl https://www.sqlite.org/2021/sqlite-autoconf-3340100.tar.gz | tar xzf -
(cd ./sqlite-autoconf-3340100 && ./configure && make && make install)
export LD_LIBRARY_PATH="/usr/local/lib"
python -c "import sqlite3; print(sqlite3.sqlite_version)"

# install skepticoin from source, already downloaded
cd skepticoin
pip install -r requirements.txt
python setup.py install

# prepare skepticoin run-time environment
mkdir -p /home/ec2-user/runtime
cd /home/ec2-user/runtime
aws s3 cp s3://$PRIVATE_BUCKET/wallet.json . > /dev/null
aws s3 cp s3://$PUBLIC_BUCKET/chain.db . > /dev/null

# Publish IP addresses back into peers.json
aws ec2 describe-instances --region $AWS_REGION --filters "Name=tag:Name,Values=skepticoin-miner" "Name=instance-state-name,Values=running" --query 'Reservations[].Instances[].[PublicIpAddress]' --output json |
     python -c "import sys, json; print(json.dumps([[row[0], 2412, 'OUTGOING'] for row in json.load(sys.stdin)]))" |
     aws s3 cp --content-type application/json --acl public-read - s3://$PUBLIC_BUCKET/peers.json

# Set things up to start skepticoin-mine on reboot. Reboot daily, publish chain.db.
crontab <<EOF
@reboot . /home/ec2-user/venv/bin/activate && cd /home/ec2-user/runtime && PYTHONUNBUFFERED=1 LD_LIBRARY_PATH="/usr/local/lib" skepticoin-mine $SKEPTICOIN_MINING_PARAMS >> $LOG 2>&1; sleep 1800 && /sbin/reboot
0 0 * * * echo 'killall skepticoin-mine; sleep 30; cd /home/ec2-user/runtime && aws s3 sync . s3://$PUBLIC_BUCKET/ --exclude "*" --include chain.db; /sbin/reboot' | at "\$(shuf -i 0-23 -n 1):\$(shuf -i 0-59 -n 1)"
EOF

# start mining
echo "rebooting to start miner"
/sbin/reboot

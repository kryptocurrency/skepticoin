import os
import io
from skepticoin.networking.params import MAX_CONNECTION_ATTEMPTS
from typing import Dict, List, Set, Tuple
from skepticoin.datatypes import Transaction
from skepticoin.networking.remote_peer import (
    ConnectedRemotePeer, DisconnectedRemotePeer, OUTGOING, load_peers_from_list
)
import json
import urllib.request
import sqlite3
from skepticoin.humans import human
from skepticoin.coinstate import CoinState
from skepticoin.serialization import stream_serialize_list


PEER_URLS: List[str] = [
    "https://pastebin.com/raw/CcfPX9mS",
    "https://skepticoin.s3.amazonaws.com/peers.json",
]


def load_peers_from_network() -> List[Tuple[str, int, str]]:

    all_peers: Set[Tuple[str, int, str]] = set()

    for url in PEER_URLS:
        print(f"downloading {url}")

        with urllib.request.urlopen(url, timeout=1) as resp:
            try:
                peers = json.loads(resp.read())
            except ValueError:
                continue

            for peer in peers:
                if len(peer) != 3:
                    continue

                all_peers.add(tuple(peer))  # type: ignore

    print("New peers.json will be created")
    return list(all_peers)


class DiskInterface:
    """Catch-all for writing to and reading from disk, factored out to facilitate testing."""

    def __init__(self) -> None:
        self.last_saved_peers: List[Tuple[str, int, str]] = []

    def load_peers(self) -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:
        try:
            db: List[Tuple[str, int, str]] = [tuple(li) for li in json.loads(open("peers.json").read())]  # type: ignore
        except Exception as e:
            print('Ignoring corrupted or missing peers.json: ' + str(e))
            db = load_peers_from_network()

        print('Loading initial list of %d peers' % len(db))
        return load_peers_from_list(db)

    def write_peers(self, peers: Dict[Tuple[str, int, str], ConnectedRemotePeer]) -> None:
        db = [(remote_peer.host, remote_peer.port, remote_peer.direction)
              for remote_peer in peers.values()
              if (remote_peer.direction == OUTGOING and remote_peer.ban_score < MAX_CONNECTION_ATTEMPTS)]

        db.sort()

        if self.last_saved_peers != db:

            if db:
                with open("peers.json", "w") as f:
                    json.dump(db, f, indent=4)
            else:
                os.remove("peers.json")

            self.last_saved_peers = db

    def write_chain_to_disk(self, coinstate: CoinState, path: str = 'chain.db') -> None:
        if not os.path.isfile(path):
            print("Creating new database: " + path)
            con = sqlite3.connect(path)
            cur = con.cursor()
            cur.execute('''CREATE TABLE chain (
                hash blob primary key,
                version int,
                height int,
                previous_block_hash blob,
                merkle_root_hash blob,
                timestamp int,
                target blob,
                nonce int,
                summary_hash blob,
                chain_sample blob,
                block_hash blob,
                transactions blob
            )''')
            con.close()

        try:
            con = sqlite3.connect(path)
            cur = con.cursor()
            for hash in coinstate.block_by_hash.keys():
                check = cur.execute("select count(*) from chain where hash=:hash", {"hash": hash}).fetchall()
                if check[0][0] == 0:
                    block = coinstate.block_by_hash[hash]
                    with io.BytesIO() as buffer:
                        stream_serialize_list(buffer, block.transactions)
                        buffer.seek(0)
                        transactions = buffer.read()
                    cur.execute("insert into chain values (?,?,?,?,?,?,?,?,?,?,?,?)", (
                        hash,
                        block.header.version,
                        block.header.summary.height,
                        block.header.summary.previous_block_hash,
                        block.header.summary.merkle_root_hash,
                        block.header.summary.timestamp,
                        block.header.summary.target,
                        block.header.summary.nonce,
                        block.header.pow_evidence.summary_hash,
                        block.header.pow_evidence.chain_sample,
                        block.header.pow_evidence.block_hash,
                        transactions
                    ))
            con.commit()

        except Exception as e:
            print('Failed to save blockchain to disk: ' + str(e))
            return
        finally:
            con.close()

    def save_transaction_for_debugging(self, transaction: Transaction) -> None:
        with open("/tmp/%s.transaction" % human(transaction.hash()), 'wb') as f:
            f.write(transaction.serialize())

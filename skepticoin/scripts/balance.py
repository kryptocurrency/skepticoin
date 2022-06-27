from datetime import datetime
from skepticoin.blockstore import DefaultBlockStore

from .utils import (
    open_or_init_wallet,
    check_chain_dir,
    read_chain_from_disk,
    configure_logging_from_args,
    start_networking_peer_in_background,
    wait_for_fresh_chain,
    DefaultArgumentParser,
)

from ..params import SASHIMI_PER_COIN


def main() -> None:
    parser = DefaultArgumentParser()
    args = parser.parse_args()
    configure_logging_from_args(args)

    check_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()

    # we need a fresh chain because our wallet doesn't track spending/receiving, so we need to look at the real
    # blockchain to know the most current balance.
    thread = start_networking_peer_in_background(args, coinstate)

    wait_for_fresh_chain(thread)
    coinstate = thread.local_peer.chain_manager.coinstate
    print("Chain up to date")

    print(
        wallet.get_balance(coinstate) / SASHIMI_PER_COIN, "SKEPTI at h. %s," % coinstate.head().height,
        datetime.fromtimestamp(coinstate.head().timestamp).isoformat())

    DefaultBlockStore.instance.flush_blocks_to_disk()

    print("Waiting for networking thread to exit.")
    thread.stop()
    thread.join()

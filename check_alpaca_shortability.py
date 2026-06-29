#!/usr/bin/env python3
"""Check Alpaca paper-account shortability flags for SOXS and SQQQ."""

from __future__ import annotations

import os
import sys

from alpaca.trading.client import TradingClient


SYMBOLS = ["SOXS", "SQQQ"]


def read_secret(name: str, fallback: str = "") -> str:
    return os.getenv(name, "") or os.getenv(fallback, "")


def main() -> None:
    key_id = read_secret("SQQQ_ALPACA_API_KEY_ID", "ALPACA_API_KEY_ID")
    secret_key = read_secret("SQQQ_ALPACA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY")
    if not key_id or not secret_key:
        sys.exit("Missing Alpaca paper API credentials.")

    client = TradingClient(key_id, secret_key, paper=True)
    account = client.get_account()
    print(f"Account equity: ${float(account.equity):,.2f}")
    print()
    print(f"{'Symbol':6s} {'Tradable':>9s} {'Shortable':>10s} {'EasyBorrow':>11s}")
    for symbol in SYMBOLS:
        asset = client.get_asset(symbol)
        print(
            f"{symbol:6s} "
            f"{str(bool(asset.tradable)):>9s} "
            f"{str(bool(asset.shortable)):>10s} "
            f"{str(bool(asset.easy_to_borrow)):>11s}"
        )


if __name__ == "__main__":
    main()

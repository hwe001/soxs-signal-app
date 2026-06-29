#!/usr/bin/env python3
"""
Paper-trading runner for the QQQ core + short SOXS overlay strategy.

This is the ONE file in this repo that places orders. Everything else
(streamlit_signal_app.py, streamlit_qqq_sqqq_app.py,
streamlit_soxs_core_app.py) is a read-only manual signal dashboard with
no broker connection. This script:

- Connects to Alpaca's PAPER trading endpoint only (paper=True). It will
  refuse to run if it cannot confirm the account is a paper account.
- Reads ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY from
  .streamlit/secrets.toml (already gitignored) via the same get_secret()
  pattern used by the dashboards, falling back to environment variables.
- Recomputes the signal from soxs_core_strategy.classify_signal() (the
  exact same logic the dashboard shows) and rebalances the account to the
  target weights every time it is run: 40% long QQQ (fixed), and short
  SOXS at 60% (normal regime) or 15% (QQQ below its 50-day MA), with the
  remainder in cash.
- Defaults to a dry run that only prints the orders it would place. Pass
  --execute to actually submit them.

Intended use: run this once per trading day (e.g. via cron, after market
open) with --execute. Running it more often will just re-flatten any
drift back to the same target weights -- harmless but unnecessary churn.

Whole-share sizing only: Alpaca does not support fractional shares for
short sells, so both legs are sized in whole shares here for consistency,
which leaves a small amount of cash unallocated versus the exact target
percentages.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import streamlit as st
import yfinance as yf
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

from soxs_core_strategy import (
    CORE_SYMBOL,
    SHORT_SYMBOL,
    QQQ_TREND_LOOKBACK,
    classify_signal,
)


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name, default)


def load_credentials() -> tuple[str, str]:
    key_id = get_secret("ALPACA_API_KEY_ID")
    secret_key = get_secret("ALPACA_API_SECRET_KEY")
    if not key_id or not secret_key:
        sys.exit(
            "Missing Alpaca paper API credentials. Add ALPACA_API_KEY_ID and "
            "ALPACA_API_SECRET_KEY to .streamlit/secrets.toml (generate paper "
            "keys at https://app.alpaca.markets/paper/dashboard/overview)."
        )
    return key_id, secret_key


def fetch_price_history(symbol: str, period: str = "1y") -> pd.Series:
    hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if hist.empty:
        sys.exit(f"No price data returned for {symbol}.")
    return hist["Close"].rename(symbol)


def build_signal_row() -> pd.Series:
    qqq = fetch_price_history(CORE_SYMBOL)
    soxs = fetch_price_history(SHORT_SYMBOL)
    df = pd.concat([qqq, soxs], axis=1, sort=True).ffill().dropna()
    df.columns = ["QQQ", "SOXS"]
    df["QQQ_MA50"] = df["QQQ"].rolling(QQQ_TREND_LOOKBACK).mean()
    return df.dropna().iloc[-1]


def get_current_qty(trading_client: TradingClient, symbol: str) -> float:
    try:
        position = trading_client.get_open_position(symbol)
        return float(position.qty)
    except Exception:
        return 0.0


def check_shortable(trading_client: TradingClient, symbol: str) -> bool:
    asset = trading_client.get_asset(symbol)
    return bool(asset.tradable and asset.shortable and asset.easy_to_borrow)


def get_latest_prices(data_client: StockHistoricalDataClient, symbols: list[str]) -> dict[str, float]:
    request = StockLatestTradeRequest(symbol_or_symbols=symbols)
    trades = data_client.get_stock_latest_trade(request)
    return {symbol: float(trades[symbol].price) for symbol in symbols}


def compute_order(symbol: str, target_qty: int, current_qty: float) -> dict | None:
    delta = target_qty - current_qty
    if abs(delta) < 1:
        return None
    side = OrderSide.BUY if delta > 0 else OrderSide.SELL
    return {"symbol": symbol, "side": side, "qty": int(abs(round(delta)))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually submit orders. Without this flag, only prints the intended orders.",
    )
    args = parser.parse_args()

    key_id, secret_key = load_credentials()
    trading_client = TradingClient(key_id, secret_key, paper=True)
    data_client = StockHistoricalDataClient(key_id, secret_key)

    account = trading_client.get_account()
    if not account.is_paper:
        sys.exit("Refusing to run: connected account is not a paper account.")
    equity = float(account.equity)

    row = build_signal_row()
    sig = classify_signal(row)

    print(f"Regime: {sig['regime']} | {sig['reason']}")
    print(f"Account equity: ${equity:,.2f}")
    print(
        f"Targets -> QQQ core: {sig['core_target_alloc']:.0%}  "
        f"SOXS short overlay: {sig['overlay_target_short_alloc']:.0%}  "
        f"Cash: {sig['target_cash_alloc']:.0%}"
    )

    if not check_shortable(trading_client, SHORT_SYMBOL):
        sys.exit(f"{SHORT_SYMBOL} is not currently shortable/easy-to-borrow on this account.")

    prices = get_latest_prices(data_client, [CORE_SYMBOL, SHORT_SYMBOL])

    target_qqq_qty = math.floor(equity * sig["core_target_alloc"] / prices[CORE_SYMBOL])
    target_soxs_qty = -math.floor(equity * sig["overlay_target_short_alloc"] / prices[SHORT_SYMBOL])

    current_qqq_qty = get_current_qty(trading_client, CORE_SYMBOL)
    current_soxs_qty = get_current_qty(trading_client, SHORT_SYMBOL)

    orders = [
        order for order in (
            compute_order(CORE_SYMBOL, target_qqq_qty, current_qqq_qty),
            compute_order(SHORT_SYMBOL, target_soxs_qty, current_soxs_qty),
        ) if order is not None
    ]

    print()
    print(f"{'Symbol':6s} {'Current Qty':>12s} {'Target Qty':>12s} {'Order':>14s}")
    print(f"{CORE_SYMBOL:6s} {current_qqq_qty:12.0f} {target_qqq_qty:12.0f} "
          f"{_describe(orders, CORE_SYMBOL):>14s}")
    print(f"{SHORT_SYMBOL:6s} {current_soxs_qty:12.0f} {target_soxs_qty:12.0f} "
          f"{_describe(orders, SHORT_SYMBOL):>14s}")

    if not orders:
        print("\nAlready at target. No orders needed.")
        return

    if not args.execute:
        print("\nDry run (no orders submitted). Pass --execute to place these orders.")
        return

    for order in orders:
        request = MarketOrderRequest(
            symbol=order["symbol"], qty=order["qty"], side=order["side"], time_in_force=TimeInForce.DAY,
        )
        result = trading_client.submit_order(request)
        print(f"Submitted: {order['side'].value.upper()} {order['qty']} {order['symbol']} -> order id {result.id}")


def _describe(orders: list[dict], symbol: str) -> str:
    for order in orders:
        if order["symbol"] == symbol:
            return f"{order['side'].value.upper()} {order['qty']}"
    return "-"


if __name__ == "__main__":
    main()

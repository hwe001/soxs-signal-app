#!/usr/bin/env python3
"""
Paper-trading runner for the QQQ core + short SQQQ hedge-overlay strategy.

This script places Alpaca PAPER orders only. It uses separate environment
variable names from the SOXS bot so both bots can run side by side:

- SQQQ_ALPACA_API_KEY_ID
- SQQQ_ALPACA_API_SECRET_KEY

By default this is a dry run. Pass --execute to submit paper orders.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from qqq_sqqq_strategy import CORE_SYMBOL, QQQ_TREND_LOOKBACK, SHORT_SYMBOL, classify_signal

REBALANCE_START_NY = time(15, 45)
REBALANCE_END_NY = time(15, 59)


def load_credentials() -> tuple[str, str]:
    key_id = os.getenv("SQQQ_ALPACA_API_KEY_ID", "")
    secret_key = os.getenv("SQQQ_ALPACA_API_SECRET_KEY", "")
    if not key_id or not secret_key:
        sys.exit(
            "Missing Alpaca paper credentials. Add GitHub Actions secrets "
            "SQQQ_ALPACA_API_KEY_ID and SQQQ_ALPACA_API_SECRET_KEY."
        )
    return key_id, secret_key


def fetch_price_history(symbol: str, period: str = "1y") -> pd.Series:
    hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if hist.empty:
        sys.exit(f"No price data returned for {symbol}.")
    return hist["Close"].rename(symbol)


def build_signal_row() -> pd.Series:
    qqq = fetch_price_history(CORE_SYMBOL)
    sqqq = fetch_price_history(SHORT_SYMBOL)
    df = pd.concat([qqq, sqqq], axis=1, sort=True).ffill().dropna()
    df.columns = ["QQQ", "SQQQ"]
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


def cancel_open_orders(trading_client: TradingClient, symbols: set[str]) -> None:
    for order in trading_client.get_orders():
        if getattr(order, "symbol", None) in symbols:
            print(f"Canceling open order {order.id} for {order.symbol}")
            trading_client.cancel_order_by_id(order.id)


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


def describe(orders: list[dict], symbol: str) -> str:
    for order in orders:
        if order["symbol"] == symbol:
            return f"{order['side'].value.upper()} {order['qty']}"
    return "-"


def should_run_now(force_run: bool) -> bool:
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    print(f"New York time: {now_ny:%Y-%m-%d %H:%M:%S}")
    if force_run:
        print("FORCE_RUN=true: bypassing market-time gate.")
        return True
    if now_ny.weekday() >= 5:
        print("Outside weekday trading schedule. Skipping.")
        return False
    if REBALANCE_START_NY <= now_ny.time() <= REBALANCE_END_NY:
        return True
    print("Outside 3:45-3:59 PM New York rebalance window. Skipping.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Submit Alpaca paper orders.")
    parser.add_argument("--force-run", action="store_true", help="Bypass the 3:45 PM New York time gate.")
    parser.add_argument("--cancel-open-orders", action="store_true", help="Cancel existing open QQQ/SQQQ orders first.")
    args = parser.parse_args()

    if not should_run_now(args.force_run):
        return

    key_id, secret_key = load_credentials()
    paper_account = True
    trading_client = TradingClient(key_id, secret_key, paper=paper_account)
    data_client = StockHistoricalDataClient(key_id, secret_key)

    account = trading_client.get_account()
    equity = float(account.equity)

    if args.cancel_open_orders and args.execute:
        cancel_open_orders(trading_client, {CORE_SYMBOL, SHORT_SYMBOL})

    row = build_signal_row()
    sig = classify_signal(row)

    print("=== QQQ + SQQQ Hedge Paper Runner ===")
    print(f"Execute orders: {args.execute} | Alpaca paper client: {paper_account}")
    print(f"Regime: {sig['regime']} | Confidence: {sig['confidence']}")
    print(f"Reason: {sig['reason']}")
    print(f"Account equity: ${equity:,.2f} | Buying power: ${float(account.buying_power):,.2f}")
    print(
        f"Targets -> QQQ core: {sig['core_target_alloc']:.0%} | "
        f"SQQQ short overlay: {sig['overlay_target_short_alloc']:.0%} | "
        f"Cash target: {sig['target_cash_alloc']:.0%}"
    )

    if not check_shortable(trading_client, SHORT_SYMBOL):
        print(f"{SHORT_SYMBOL} is not currently shortable/easy-to-borrow on this account.")
        print("Skipping all orders because the strategy requires a short SQQQ overlay.")
        return

    prices = get_latest_prices(data_client, [CORE_SYMBOL, SHORT_SYMBOL])
    target_qqq_qty = math.floor(equity * sig["core_target_alloc"] / prices[CORE_SYMBOL])
    target_sqqq_qty = -math.floor(equity * sig["overlay_target_short_alloc"] / prices[SHORT_SYMBOL])

    current_qqq_qty = get_current_qty(trading_client, CORE_SYMBOL)
    current_sqqq_qty = get_current_qty(trading_client, SHORT_SYMBOL)

    orders = [
        order for order in (
            compute_order(CORE_SYMBOL, target_qqq_qty, current_qqq_qty),
            compute_order(SHORT_SYMBOL, target_sqqq_qty, current_sqqq_qty),
        ) if order is not None
    ]

    print()
    print(f"{'Symbol':6s} {'Price':>10s} {'Current Qty':>12s} {'Target Qty':>12s} {'Order':>14s}")
    print(
        f"{CORE_SYMBOL:6s} {prices[CORE_SYMBOL]:10.2f} {current_qqq_qty:12.0f} "
        f"{target_qqq_qty:12.0f} {describe(orders, CORE_SYMBOL):>14s}"
    )
    print(
        f"{SHORT_SYMBOL:6s} {prices[SHORT_SYMBOL]:10.2f} {current_sqqq_qty:12.0f} "
        f"{target_sqqq_qty:12.0f} {describe(orders, SHORT_SYMBOL):>14s}"
    )

    if not orders:
        print("\nAlready at target. No orders needed.")
        return

    if not args.execute:
        print("\nDry run only. Set SQQQ_EXECUTE_ORDERS=true or workflow input=true to submit paper orders.")
        return

    for order in orders:
        request = MarketOrderRequest(
            symbol=order["symbol"],
            qty=order["qty"],
            side=order["side"],
            time_in_force=TimeInForce.DAY,
        )
        result = trading_client.submit_order(request)
        print(f"Submitted: {order['side'].value.upper()} {order['qty']} {order['symbol']} | Status: {result.status}")


if __name__ == "__main__":
    main()

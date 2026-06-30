#!/usr/bin/env python3
"""
Paper-trading runner for the HIVE equity + QQQ long-term core strategy.

Executes QQQ and HIVE equity orders on Alpaca paper accounts.
Options overlay signals are printed as advisory only (Alpaca paper does not support options).

Secrets required:
  HIVE_QQQ_ALPACA_API_KEY_ID
  HIVE_QQQ_ALPACA_API_SECRET_KEY
  HIVE_QQQ_EXECUTE_ORDERS  (set to "true" to submit orders)

Pass --execute to submit paper orders. Default is dry-run.
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

from hive_qqq_strategy import (
    BTC_SYMBOL,
    BTC_TREND_LOOKBACK,
    HIVE_LOOKBACK,
    HIVE_SYMBOL,
    QQQ_SYMBOL,
    QQQ_TREND_LOOKBACK,
    VIX_SYMBOL,
    classify_signal,
)

REBALANCE_START_NY = time(15, 45)
REBALANCE_END_NY = time(15, 59)


def load_credentials() -> tuple[str, str]:
    key_id = os.getenv("HIVE_QQQ_ALPACA_API_KEY_ID", "") or os.getenv("ALPACA_API_KEY_ID", "")
    secret_key = os.getenv("HIVE_QQQ_ALPACA_API_SECRET_KEY", "") or os.getenv("ALPACA_API_SECRET_KEY", "")
    if not key_id or not secret_key:
        sys.exit(
            "Missing Alpaca paper credentials. Set HIVE_QQQ_ALPACA_API_KEY_ID and "
            "HIVE_QQQ_ALPACA_API_SECRET_KEY as environment variables or GitHub Actions secrets."
        )
    return key_id, secret_key


def fetch_price_history(symbol: str, period: str = "1y") -> pd.Series:
    hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if hist.empty:
        sys.exit(f"No price data returned for {symbol}.")
    return hist["Close"]


def build_signal_row() -> pd.Series:
    qqq = fetch_price_history(QQQ_SYMBOL)
    hive = fetch_price_history(HIVE_SYMBOL)
    btc = fetch_price_history(BTC_SYMBOL)
    vix = fetch_price_history(VIX_SYMBOL)

    df = pd.concat(
        {"QQQ": qqq, "HIVE": hive, "BTC": btc, "VIX": vix},
        axis=1,
    ).sort_index()
    # Keep only rows where equity data is present (trading days); BTC fills forward.
    df = df[df["QQQ"].notna()].ffill().dropna()
    df["QQQ_MA50"] = df["QQQ"].rolling(QQQ_TREND_LOOKBACK).mean()
    df["BTC_MA20"] = df["BTC"].rolling(BTC_TREND_LOOKBACK).mean()
    df["HIVE_MA20"] = df["HIVE"].rolling(HIVE_LOOKBACK).mean()
    return df.dropna().iloc[-1]


def get_current_qty(trading_client: TradingClient, symbol: str) -> float:
    try:
        position = trading_client.get_open_position(symbol)
        return float(position.qty)
    except Exception:
        return 0.0


def cancel_open_orders(trading_client: TradingClient, symbols: set[str]) -> None:
    for order in trading_client.get_orders():
        if getattr(order, "symbol", None) in symbols:
            print(f"Canceling open order {order.id} for {order.symbol}")
            trading_client.cancel_order_by_id(order.id)


def get_latest_prices(
    data_client: StockHistoricalDataClient, symbols: list[str]
) -> dict[str, float]:
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
        print("--force-run: bypassing market-time gate.")
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
    parser.add_argument(
        "--cancel-open-orders",
        action="store_true",
        help="Cancel existing open QQQ/HIVE orders before rebalancing.",
    )
    args = parser.parse_args()

    if not should_run_now(args.force_run):
        return

    key_id, secret_key = load_credentials()
    trading_client = TradingClient(key_id, secret_key, paper=True)
    data_client = StockHistoricalDataClient(key_id, secret_key)

    account = trading_client.get_account()
    equity = float(account.equity)

    if args.cancel_open_orders and args.execute:
        cancel_open_orders(trading_client, {QQQ_SYMBOL, HIVE_SYMBOL})

    row = build_signal_row()
    sig = classify_signal(row)

    print("=== HIVE Equity + QQQ Long-Term Core Paper Runner ===")
    print(f"Execute orders: {args.execute}")
    print(f"Regime: {sig['regime']} | Confidence: {sig['confidence']}")
    print(f"Reason: {sig['reason']}")
    print(f"Account equity: ${equity:,.2f} | Buying power: ${float(account.buying_power):,.2f}")
    print()
    print(f"Market signals:")
    print(f"  BTC: ${sig['btc']:,.0f}  MA20: ${sig['btc_ma20']:,.0f}  {'ABOVE' if sig['btc_above_ma20'] else 'BELOW'} MA20")
    print(f"  QQQ: ${sig['qqq']:.2f}  MA50: ${sig['qqq_ma50']:.2f}  {'ABOVE' if sig['qqq_above_ma50'] else 'BELOW'} MA50")
    print(f"  HIVE: ${sig['hive']:.4f}  MA20: ${sig['hive_ma20']:.4f}  {'ABOVE' if sig['hive_above_ma20'] else 'BELOW'} MA20")
    print(f"  VIX: {sig['vix']:.2f}")
    print()
    print(
        f"Targets: QQQ {sig['qqq_target_alloc']:.0%} | "
        f"HIVE {sig['hive_target_alloc']:.0%} | "
        f"Cash {sig['target_cash_alloc']:.0%}"
    )
    print()
    print(f"[OPTIONS ADVISORY — not executed]")
    print(f"  Action: {sig['options_action']}")
    print(f"  {sig['options_detail']}")
    print()

    prices = get_latest_prices(data_client, [QQQ_SYMBOL, HIVE_SYMBOL])
    target_qqq_qty = math.floor(equity * sig["qqq_target_alloc"] / prices[QQQ_SYMBOL])
    target_hive_qty = (
        math.floor(equity * sig["hive_target_alloc"] / prices[HIVE_SYMBOL])
        if sig["hive_target_alloc"] > 0
        else 0
    )

    current_qqq_qty = get_current_qty(trading_client, QQQ_SYMBOL)
    current_hive_qty = get_current_qty(trading_client, HIVE_SYMBOL)

    orders = [
        o for o in (
            compute_order(QQQ_SYMBOL, target_qqq_qty, current_qqq_qty),
            compute_order(HIVE_SYMBOL, target_hive_qty, current_hive_qty),
        )
        if o is not None
    ]

    print(f"{'Symbol':6s} {'Price':>10s} {'Current Qty':>12s} {'Target Qty':>12s} {'Order':>14s}")
    print(
        f"{QQQ_SYMBOL:6s} {prices[QQQ_SYMBOL]:10.2f} {current_qqq_qty:12.0f} "
        f"{target_qqq_qty:12.0f} {describe(orders, QQQ_SYMBOL):>14s}"
    )
    print(
        f"{HIVE_SYMBOL:6s} {prices[HIVE_SYMBOL]:10.4f} {current_hive_qty:12.0f} "
        f"{target_hive_qty:12.0f} {describe(orders, HIVE_SYMBOL):>14s}"
    )

    if not orders:
        print("\nAlready at target. No orders needed.")
        return

    if not args.execute:
        execute_env = os.getenv("HIVE_QQQ_EXECUTE_ORDERS", "")
        print(
            "\nDry run only. Pass --execute or set HIVE_QQQ_EXECUTE_ORDERS=true "
            "to submit paper orders."
        )
        if execute_env == "true":
            print("Note: HIVE_QQQ_EXECUTE_ORDERS is 'true' but --execute flag was not passed.")
        return

    for order in orders:
        request = MarketOrderRequest(
            symbol=order["symbol"],
            qty=order["qty"],
            side=order["side"],
            time_in_force=TimeInForce.DAY,
        )
        result = trading_client.submit_order(request)
        print(
            f"Submitted: {order['side'].value.upper()} {order['qty']} {order['symbol']} "
            f"| Status: {result.status}"
        )


if __name__ == "__main__":
    main()

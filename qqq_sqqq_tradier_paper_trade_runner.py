#!/usr/bin/env python3
"""
Tradier runner for the QQQ core + short SOXS overlay strategy.

Defaults to the Tradier sandbox environment and to a dry run. Pass --execute
to submit orders, and set TRADIER_SANDBOX=false to point at the production
Tradier API (real account, real money) instead of the sandbox.

Required environment variables:
- TRADIER_TOKEN: Tradier OAuth access token (sandbox or production).
- TRADIER_ACCOUNT_ID: Tradier account number the token is authorized for.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

from qqq_sqqq_strategy import CORE_SYMBOL, QQQ_TREND_LOOKBACK, SHORT_SYMBOL, classify_signal

REBALANCE_START_NY = time(15, 45)
REBALANCE_END_NY = time(15, 59)

SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1"
PRODUCTION_BASE_URL = "https://api.tradier.com/v1"


def load_credentials() -> tuple[str, str, str]:
    token = os.getenv("TRADIER_TOKEN", "")
    account_id = os.getenv("TRADIER_ACCOUNT_ID", "")
    if not token or not account_id:
        sys.exit("Missing Tradier credentials. Set TRADIER_TOKEN and TRADIER_ACCOUNT_ID.")
    sandbox = os.getenv("TRADIER_SANDBOX", "true").lower() != "false"
    base_url = SANDBOX_BASE_URL if sandbox else PRODUCTION_BASE_URL
    return token, account_id, base_url


def tradier_request(method: str, base_url: str, token: str, path: str, **kwargs) -> dict:
    response = requests.request(
        method,
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=15,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


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


def get_account_equity(base_url: str, token: str, account_id: str) -> float:
    data = tradier_request("GET", base_url, token, f"/accounts/{account_id}/balances")
    return float(data["balances"]["total_equity"])


def get_positions(base_url: str, token: str, account_id: str) -> dict[str, float]:
    data = tradier_request("GET", base_url, token, f"/accounts/{account_id}/positions")
    positions = data.get("positions")
    if not positions or positions == "null":
        return {}
    items = positions["position"]
    if isinstance(items, dict):
        items = [items]
    # Tradier reports short equity positions as a negative quantity.
    return {item["symbol"]: float(item["quantity"]) for item in items}


def get_quotes(base_url: str, token: str, symbols: list[str]) -> dict[str, float]:
    data = tradier_request(
        "GET", base_url, token, "/markets/quotes", params={"symbols": ",".join(symbols)}
    )
    quotes = data["quotes"]["quote"]
    if isinstance(quotes, dict):
        quotes = [quotes]
    return {quote["symbol"]: float(quote["last"]) for quote in quotes}


def compute_order(symbol: str, target_qty: int, current_qty: float, is_short: bool) -> dict | None:
    delta = target_qty - current_qty
    if abs(delta) < 1:
        return None
    qty = int(abs(round(delta)))
    if is_short:
        side = "sell_short" if delta < 0 else "buy_to_cover"
    else:
        side = "buy" if delta > 0 else "sell"
    return {"symbol": symbol, "side": side, "qty": qty}


def describe(orders: list[dict], symbol: str) -> str:
    for order in orders:
        if order["symbol"] == symbol:
            return f"{order['side'].upper()} {order['qty']}"
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


def submit_order(base_url: str, token: str, account_id: str, order: dict) -> dict:
    return tradier_request(
        "POST",
        base_url,
        token,
        f"/accounts/{account_id}/orders",
        data={
            "class": "equity",
            "symbol": order["symbol"],
            "side": order["side"],
            "quantity": order["qty"],
            "type": "market",
            "duration": "day",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Submit Tradier orders.")
    parser.add_argument("--force-run", action="store_true", help="Bypass the 3:45 PM New York time gate.")
    args = parser.parse_args()

    if not should_run_now(args.force_run):
        return

    token, account_id, base_url = load_credentials()
    sandbox = base_url == SANDBOX_BASE_URL

    equity = get_account_equity(base_url, token, account_id)

    row = build_signal_row()
    sig = classify_signal(row)

    print("=== QQQ + SOXS Core Overlay Tradier Runner ===")
    print(f"Execute orders: {args.execute} | Tradier sandbox: {sandbox}")
    print(f"Regime: {sig['regime']} | Confidence: {sig['confidence']}")
    print(f"Reason: {sig['reason']}")
    print(f"Account equity: ${equity:,.2f}")
    print(
        f"Targets -> QQQ core: {sig['core_target_alloc']:.0%} | "
        f"SOXS short overlay: {sig['overlay_target_short_alloc']:.0%} | "
        f"Cash target: {sig['target_cash_alloc']:.0%}"
    )

    prices = get_quotes(base_url, token, [CORE_SYMBOL, SHORT_SYMBOL])
    positions = get_positions(base_url, token, account_id)
    current_qqq_qty = positions.get(CORE_SYMBOL, 0.0)
    current_short_qty = positions.get(SHORT_SYMBOL, 0.0)

    target_qqq_qty = math.floor(equity * sig["core_target_alloc"] / prices[CORE_SYMBOL])
    target_short_qty = -math.floor(equity * sig["overlay_target_short_alloc"] / prices[SHORT_SYMBOL])

    orders = [
        order for order in (
            compute_order(CORE_SYMBOL, target_qqq_qty, current_qqq_qty, is_short=False),
            compute_order(SHORT_SYMBOL, target_short_qty, current_short_qty, is_short=True),
        ) if order is not None
    ]

    print()
    print(f"{'Symbol':6s} {'Price':>10s} {'Current Qty':>12s} {'Target Qty':>12s} {'Order':>14s}")
    print(
        f"{CORE_SYMBOL:6s} {prices[CORE_SYMBOL]:10.2f} {current_qqq_qty:12.0f} "
        f"{target_qqq_qty:12.0f} {describe(orders, CORE_SYMBOL):>14s}"
    )
    print(
        f"{SHORT_SYMBOL:6s} {prices[SHORT_SYMBOL]:10.2f} {current_short_qty:12.0f} "
        f"{target_short_qty:12.0f} {describe(orders, SHORT_SYMBOL):>14s}"
    )

    if not orders:
        print("\nAlready at target. No orders needed.")
        return

    if not args.execute:
        print("\nDry run only. Pass --execute to submit Tradier orders.")
        return

    for order in orders:
        result = submit_order(base_url, token, account_id, order)
        submitted = result.get("order", {})
        print(
            f"Submitted: {order['side'].upper()} {order['qty']} {order['symbol']} | "
            f"Status: {submitted.get('status')} | Order ID: {submitted.get('id')}"
        )


if __name__ == "__main__":
    main()

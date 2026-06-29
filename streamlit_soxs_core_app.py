#!/usr/bin/env python3
"""
Streamlit Cash + Short SOXS Core Manual Signal Dashboard.

Strategy (backtested over 10 years, see repo history for the analysis):
- No QQQ is ever held. QQQ's 50-day trend is used purely as an external
  signal to gate a short SOXS position sized as a fraction of NAV; the rest
  of the book sits in cash.
- When QQQ is above its 50-day MA, hold a 40% short SOXS position,
  harvesting leveraged-ETF decay.
- When QQQ loses its 50-day trend, cut the short back to a 15% floor
  rather than fully covering it.

This intentionally skips VIX-band gating, spike/fade entry timing, and an
RSI throttle — consistent with the QQQ/SQQQ overlay backtest, a single
50-day trend filter captured nearly all of the available risk reduction
here too. Against the original elaborate SOXS-only logic (VIX bands +
spike/fade + RSI throttle), this simpler design has a lower CAGR (29.1%
vs 33.4%) but a better Sharpe (0.98 vs 0.95), better Calmar (0.72 vs 0.70),
and a much shallower max drawdown (-40.6% vs -47.9%) over the same
2016-2026 window.

Public-safe version:
- No Alpaca integration
- No order execution
- No broker credentials
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf


CORE_SYMBOL = "QQQ"
SHORT_SYMBOL = "SOXS"
VIX_SYMBOL = "^VIX"

NORMAL_SHORT_ALLOC = 0.40
TREND_BROKEN_SHORT_ALLOC = 0.15

QQQ_TREND_LOOKBACK = 50


st.set_page_config(page_title="Cash + Short SOXS Signal", page_icon="🩳", layout="wide")


def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def password_gate() -> bool:
    password = get_secret("SIGNAL_APP_PASSWORD", "")
    if not password:
        return True

    st.sidebar.subheader("Access")
    entered = st.sidebar.text_input("Password", type="password")
    if entered == password:
        return True
    if entered:
        st.sidebar.error("Incorrect password")
    st.info("Enter the dashboard password in the sidebar.")
    return False


@st.cache_data(ttl=300)
def fetch_history(symbol: str, period: str = "1y") -> pd.Series:
    last_error = None
    for attempt in range(3):
        try:
            hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
            if not hist.empty:
                return hist["Close"].rename(symbol.replace("^", ""))
        except Exception as exc:
            last_error = exc
        time.sleep(1 + attempt)
    raise RuntimeError(f"No data for {symbol}. Last error: {last_error}")


def build_data() -> pd.DataFrame:
    qqq = fetch_history(CORE_SYMBOL)
    soxs = fetch_history(SHORT_SYMBOL)
    vix = fetch_history(VIX_SYMBOL)
    df = pd.concat([qqq, soxs, vix], axis=1, sort=True).ffill().dropna()
    df.columns = ["QQQ", "SOXS", "VIX"]
    df["QQQ_MA50"] = df["QQQ"].rolling(QQQ_TREND_LOOKBACK).mean()
    return df.dropna()


def signal(
    regime: str,
    action: str,
    short_alloc: float,
    confidence: str,
    reason: str,
    row: pd.Series,
) -> dict:
    cash_alloc = 1.0 - short_alloc
    return {
        "timestamp_ny": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "action": action,
        "target_short_alloc": short_alloc,
        "target_cash_alloc": cash_alloc,
        "confidence": confidence,
        "reason": reason,
        "qqq": float(row["QQQ"]),
        "qqq_ma50": float(row["QQQ_MA50"]),
        "qqq_below_ma50": bool(float(row["QQQ"]) < float(row["QQQ_MA50"])),
        "soxs": float(row["SOXS"]),
        "vix": float(row["VIX"]),
    }


def classify_signal(row: pd.Series) -> dict:
    qqq_below_ma50 = float(row["QQQ"]) < float(row["QQQ_MA50"])

    if qqq_below_ma50:
        return signal(
            "trend_broken", "REDUCE SOXS SHORT TOWARD FLOOR", TREND_BROKEN_SHORT_ALLOC, "high",
            "QQQ is below its 50-day trend; cut the short SOXS position back to a 15% floor "
            "rather than fully covering it. No QQQ is held; the rest of the book is cash.", row,
        )
    return signal(
        "normal", "HOLD / ADD SOXS SHORT TOWARD TARGET", NORMAL_SHORT_ALLOC, "medium",
        "QQQ is above its 50-day trend; hold the full 40% short SOXS position to harvest "
        "leveraged-ETF decay. No QQQ is held; the rest of the book is cash.", row,
    )


def pct(x: float) -> str:
    return f"{x:.1%}"


def render_dashboard() -> None:
    st.title("Cash + Short SOXS Core Signal")
    st.caption(
        "Manual guide only. No broker connection. No order execution. "
        "No QQQ is ever held; QQQ is used only as a trend signal."
    )

    if st.button("Refresh market data"):
        st.cache_data.clear()
        st.rerun()

    df = build_data()
    sig = classify_signal(df.iloc[-1])

    st.subheader(sig["action"])
    st.write(sig["reason"])
    st.caption(f"New York time: {sig['timestamp_ny']}")

    cols = st.columns(4)
    cols[0].metric("Regime", sig["regime"])
    cols[1].metric("Short SOXS Target", pct(sig["target_short_alloc"]))
    cols[2].metric("Cash Target", pct(sig["target_cash_alloc"]))
    cols[3].metric("Confidence", sig["confidence"])

    cols = st.columns(4)
    cols[0].metric("QQQ (signal only)", f"${sig['qqq']:.2f}")
    cols[1].metric("QQQ MA50", f"${sig['qqq_ma50']:.2f}")
    cols[2].metric("QQQ Below MA50", "Yes" if sig["qqq_below_ma50"] else "No")
    cols[3].metric("VIX (context only)", f"{sig['vix']:.2f}")

    st.divider()
    st.line_chart(df[["QQQ", "QQQ_MA50"]].tail(180))
    st.line_chart(df[["SOXS"]].tail(180))
    st.line_chart(df[["VIX"]].tail(180))

    st.subheader("Recent Data")
    st.dataframe(df.tail(20).round(2), use_container_width=True)

    st.download_button(
        "Download JSON signal",
        data=pd.Series(sig).to_json(indent=2),
        file_name="soxs_core_signal.json",
        mime="application/json",
    )


if password_gate():
    try:
        render_dashboard()
    except Exception as exc:
        st.error(f"Could not generate signal: {exc}")

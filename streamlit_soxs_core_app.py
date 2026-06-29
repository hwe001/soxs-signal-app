#!/usr/bin/env python3
"""
Streamlit QQQ Core + Short SOXS Overlay Manual Signal Dashboard.

Strategy (backtested over 10 years, see repo history for the analysis):
- Core leg: long QQQ at a fixed 40% weight, held regardless of regime.
- Overlay leg: short SOXS at a fixed 60% weight whenever QQQ is above its
  50-day MA, harvesting leveraged-ETF decay. When the trend breaks, the
  overlay is cut back to a 15% floor rather than fully covered.
- The remainder of NAV (40-45% depending on regime) sits in cash.

This intentionally skips VIX-band gating, spike/fade entry timing, and an
RSI throttle — consistent with the QQQ/SQQQ overlay backtest, a single
50-day trend filter captured nearly all of the available risk reduction
here too. Adding the 40% QQQ core to a 60%/15% SOXS-only overlay actually
improves risk-adjusted returns (Sharpe 1.01 vs 0.96, Calmar 0.81 vs 0.72)
because QQQ-long and SOXS-short are not perfectly correlated (broad market
vs. semiconductor-sector decay), even though it raises CAGR to 46.7% and
deepens max drawdown to -57.7% over the 2016-2026 window.

Dividend/distribution handling: prices are fetched dividend-adjusted
(Yahoo's adjusted close, i.e. `auto_adjust=True`). For the short SOXS leg,
`-pct_change(adjusted_close)` already nets the ex-distribution price-drop
benefit against the payment-in-lieu-of-dividend owed to the share lender,
so the short's economic return is correct without a separate adjustment.
The cost of borrowing the shares (stock-loan fee) is a distinct cost and
is modeled separately in the backtest, not in this dashboard.

Public-safe version:
- No Alpaca integration
- No order execution
- No broker credentials
"""

from __future__ import annotations

import os
import time

import pandas as pd
import streamlit as st
import yfinance as yf

from soxs_core_strategy import (
    CORE_SYMBOL,
    SHORT_SYMBOL,
    VIX_SYMBOL,
    CORE_ALLOC,
    NORMAL_SHORT_ALLOC,
    TREND_BROKEN_SHORT_ALLOC,
    QQQ_TREND_LOOKBACK,
    classify_signal,
)


st.set_page_config(page_title="QQQ Core + SOXS Overlay Signal", page_icon="🩳", layout="wide")


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


def pct(x: float) -> str:
    return f"{x:.1%}"


def render_dashboard() -> None:
    st.title("QQQ Core + Short SOXS Overlay Signal")
    st.caption("Manual guide only. No broker connection. No order execution.")

    if st.button("Refresh market data"):
        st.cache_data.clear()
        st.rerun()

    df = build_data()
    last_row = df.iloc[-1]
    sig = classify_signal(last_row)

    st.subheader(sig["overlay_action"])
    st.write(sig["reason"])
    st.caption(f"Core leg: {sig['core_action']} | New York time: {sig['timestamp_ny']}")

    cols = st.columns(4)
    cols[0].metric("Regime", sig["regime"])
    cols[1].metric("Core QQQ Target", pct(sig["core_target_alloc"]))
    cols[2].metric("Overlay SOXS Short Target", pct(sig["overlay_target_short_alloc"]))
    cols[3].metric("Cash Target", pct(sig["target_cash_alloc"]))

    cols = st.columns(4)
    cols[0].metric("QQQ", f"${sig['qqq']:.2f}")
    cols[1].metric("QQQ MA50", f"${sig['qqq_ma50']:.2f}")
    cols[2].metric("QQQ Below MA50", "Yes" if sig["qqq_below_ma50"] else "No")
    cols[3].metric("VIX (context only)", f"{last_row['VIX']:.2f}")

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

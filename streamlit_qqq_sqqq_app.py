#!/usr/bin/env python3
"""
Streamlit QQQ Core / SQQQ Hedge-Overlay Manual Signal Dashboard.

Strategy (backtested over 10 years, see repo history for the analysis):
- Core leg: long QQQ (buy-and-hold), trimmed defensively when QQQ loses its
  50-day trend.
- Overlay leg: short SQQQ at a fixed 40% weight whenever QQQ is above its
  50-day MA, harvesting leveraged-ETF decay alongside the long core. When
  the trend breaks, the overlay is cut back to a small 5% floor rather than
  fully covered.

This intentionally skips VIX-band gating, fast squeeze valves, and
spike/fade entry timing — a 10-year backtest found that extra complexity
on top of the 50-day trend filter didn't improve risk-adjusted returns (and
a fast reactive squeeze valve was actively harmful, causing whipsaw losses
by covering and immediately re-shorting at worse levels). The single trend
filter captured nearly all of the available risk reduction.

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
SHORT_SYMBOL = "SQQQ"
VIX_SYMBOL = "^VIX"

CORE_FULL_ALLOC = 1.00
CORE_DEFENSIVE_ALLOC = 0.75

NORMAL_SHORT_ALLOC = 0.40
TREND_BROKEN_SHORT_ALLOC = 0.05

QQQ_TREND_LOOKBACK = 50


st.set_page_config(page_title="QQQ/SQQQ Hedge Signal", page_icon="🛡️", layout="wide")


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
    sqqq = fetch_history(SHORT_SYMBOL)
    vix = fetch_history(VIX_SYMBOL)
    df = pd.concat([qqq, sqqq, vix], axis=1, sort=True).ffill().dropna()
    df.columns = ["QQQ", "SQQQ", "VIX"]
    df["QQQ_MA50"] = df["QQQ"].rolling(QQQ_TREND_LOOKBACK).mean()
    return df.dropna()


def signal(
    regime: str,
    core_action: str,
    core_alloc: float,
    overlay_action: str,
    overlay_alloc: float,
    confidence: str,
    reason: str,
    row: pd.Series,
) -> dict:
    return {
        "timestamp_ny": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "core_action": core_action,
        "core_target_alloc": core_alloc,
        "overlay_action": overlay_action,
        "overlay_target_short_alloc": overlay_alloc,
        "confidence": confidence,
        "reason": reason,
        "qqq": float(row["QQQ"]),
        "qqq_ma50": float(row["QQQ_MA50"]),
        "qqq_below_ma50": bool(float(row["QQQ"]) < float(row["QQQ_MA50"])),
        "sqqq": float(row["SQQQ"]),
        "vix": float(row["VIX"]),
    }


def classify_core(row: pd.Series) -> tuple[str, float]:
    if float(row["QQQ"]) < float(row["QQQ_MA50"]):
        return "TRIM CORE QQQ TOWARD DEFENSIVE WEIGHT", CORE_DEFENSIVE_ALLOC
    return "HOLD FULL CORE QQQ", CORE_FULL_ALLOC


def classify_signal(row: pd.Series) -> dict:
    qqq_below_ma50 = float(row["QQQ"]) < float(row["QQQ_MA50"])
    core_action, core_alloc = classify_core(row)

    if qqq_below_ma50:
        return signal(
            "trend_broken", core_action, core_alloc,
            "REDUCE SQQQ SHORT TOWARD FLOOR", TREND_BROKEN_SHORT_ALLOC, "high",
            "QQQ is below its 50-day trend; cut the short overlay back to a small floor "
            "position rather than fully covering it.", row,
        )
    return signal(
        "normal", core_action, core_alloc,
        "HOLD / ADD SQQQ SHORT TOWARD TARGET", NORMAL_SHORT_ALLOC, "medium",
        "QQQ is above its 50-day trend; hold the full short SQQQ overlay to harvest "
        "leveraged-ETF decay alongside the long core.", row,
    )


def pct(x: float) -> str:
    return f"{x:.1%}"


def render_dashboard() -> None:
    st.title("QQQ Core + SQQQ Hedge Overlay Signal")
    st.caption("Manual guide only. No broker connection. No order execution.")

    if st.button("Refresh market data"):
        st.cache_data.clear()
        st.rerun()

    df = build_data()
    sig = classify_signal(df.iloc[-1])

    st.subheader(sig["overlay_action"])
    st.write(sig["reason"])
    st.caption(f"Core leg: {sig['core_action']} | New York time: {sig['timestamp_ny']}")

    cols = st.columns(4)
    cols[0].metric("Regime", sig["regime"])
    cols[1].metric("Core QQQ Target", pct(sig["core_target_alloc"]))
    cols[2].metric("Overlay SQQQ Short Target", pct(sig["overlay_target_short_alloc"]))
    cols[3].metric("Confidence", sig["confidence"])

    cols = st.columns(4)
    cols[0].metric("QQQ", f"${sig['qqq']:.2f}")
    cols[1].metric("QQQ MA50", f"${sig['qqq_ma50']:.2f}")
    cols[2].metric("QQQ Below MA50", "Yes" if sig["qqq_below_ma50"] else "No")
    cols[3].metric("VIX (context only)", f"{sig['vix']:.2f}")

    st.divider()
    st.line_chart(df[["QQQ", "QQQ_MA50"]].tail(180))
    st.line_chart(df[["SQQQ"]].tail(180))
    st.line_chart(df[["VIX"]].tail(180))

    st.subheader("Recent Data")
    st.dataframe(df.tail(20).round(2), use_container_width=True)

    st.download_button(
        "Download JSON signal",
        data=pd.Series(sig).to_json(indent=2),
        file_name="qqq_sqqq_hedge_signal.json",
        mime="application/json",
    )


if password_gate():
    try:
        render_dashboard()
    except Exception as exc:
        st.error(f"Could not generate signal: {exc}")

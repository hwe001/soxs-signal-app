#!/usr/bin/env python3
"""
Streamlit SOXS Manual Signal Dashboard.

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

NORMAL_SHORT_ALLOC = 0.50
CAUTION_SHORT_ALLOC = 0.25
DANGER_SHORT_ALLOC = 0.15
EMERGENCY_SHORT_ALLOC = 0.00

VIX_CAUTION = 35.0
VIX_DANGER = 45.0
VIX_EMERGENCY = 55.0

SOXS_HIGH_LOOKBACK = 20
QQQ_MA_LOOKBACK = 20
RSI_PERIOD = 14


st.set_page_config(page_title="SOXS Signal", page_icon="📈", layout="wide")


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
def fetch_history(symbol: str, period: str = "6mo") -> pd.Series:
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


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - 100 / (1 + rs)


def build_data() -> pd.DataFrame:
    qqq = fetch_history(CORE_SYMBOL)
    soxs = fetch_history(SHORT_SYMBOL)
    vix = fetch_history(VIX_SYMBOL)
    df = pd.concat([qqq, soxs, vix], axis=1, sort=True).ffill().dropna()
    df.columns = ["QQQ", "SOXS", "VIX"]
    df["QQQ_MA20"] = df["QQQ"].rolling(QQQ_MA_LOOKBACK).mean()
    df["QQQ_RSI14"] = rsi(df["QQQ"])
    df["SOXS_MA5"] = df["SOXS"].rolling(5).mean()
    df["SOXS_MA20"] = df["SOXS"].rolling(20).mean()
    df["SOXS_HIGH20"] = df["SOXS"].rolling(SOXS_HIGH_LOOKBACK).max()
    df["SOXS_PULLBACK_FROM_HIGH20"] = df["SOXS"] / df["SOXS_HIGH20"] - 1.0
    return df.dropna()


def signal(regime: str, action: str, confidence: str, target_alloc: float, reason: str, row: pd.Series) -> dict:
    return {
        "timestamp_ny": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "action": action,
        "confidence": confidence,
        "target_short_alloc": target_alloc,
        "reason": reason,
        "qqq": float(row["QQQ"]),
        "qqq_ma20": float(row["QQQ_MA20"]),
        "qqq_rsi14": float(row["QQQ_RSI14"]),
        "qqq_below_ma20": bool(float(row["QQQ"]) < float(row["QQQ_MA20"])),
        "soxs": float(row["SOXS"]),
        "soxs_ma5": float(row["SOXS_MA5"]),
        "soxs_ma20": float(row["SOXS_MA20"]),
        "soxs_high20": float(row["SOXS_HIGH20"]),
        "soxs_pullback_from_high20": float(row["SOXS_PULLBACK_FROM_HIGH20"]),
        "soxs_at_high20": bool(float(row["SOXS"]) >= float(row["SOXS_HIGH20"]) * 0.98),
        "vix": float(row["VIX"]),
    }


def classify_signal(row: pd.Series) -> dict:
    vix = float(row["VIX"])
    qqq = float(row["QQQ"])
    qqq_ma20 = float(row["QQQ_MA20"])
    qqq_rsi = float(row["QQQ_RSI14"])
    soxs = float(row["SOXS"])
    soxs_ma5 = float(row["SOXS_MA5"])
    soxs_high20 = float(row["SOXS_HIGH20"])
    soxs_pullback = float(row["SOXS_PULLBACK_FROM_HIGH20"])

    soxs_at_high = soxs >= soxs_high20 * 0.98
    qqq_below_ma = qqq < qqq_ma20
    soxs_breaking_down = soxs < soxs_ma5 and soxs_pullback <= -0.08

    if vix >= VIX_EMERGENCY:
        return signal("emergency", "COVER / FLATTEN SOXS SHORT", "high", EMERGENCY_SHORT_ALLOC, "VIX is in crisis territory; short SOXS tail risk dominates.", row)
    if vix >= VIX_DANGER:
        return signal("danger", "REDUCE SOXS SHORT / DO NOT ADD", "high", DANGER_SHORT_ALLOC, "VIX is very elevated; reduce exposure and avoid adding into panic.", row)
    if vix >= VIX_CAUTION:
        return signal("caution", "HOLD SMALL SHORT OR REDUCE; DO NOT ADD", "medium", CAUTION_SHORT_ALLOC, "VIX is elevated; wait for clearer panic fade.", row)
    if soxs_at_high:
        if soxs_breaking_down and not qqq_below_ma:
            return signal("soxs_spike", "START / ADD SMALL SOXS SHORT", "medium", CAUTION_SHORT_ALLOC, "SOXS has spiked but is beginning to fade while QQQ is healthier.", row)
        return signal("soxs_spike", "WAIT; DO NOT SHORT VERTICAL SPIKE", "high", CAUTION_SHORT_ALLOC, "SOXS is near its 20-day high; wait for pullback confirmation.", row)
    if qqq_below_ma:
        return signal("qqq_soft", "HOLD OR REDUCE; DO NOT ADD", "medium", CAUTION_SHORT_ALLOC, "QQQ is below its 20-day moving average; avoid increasing short SOXS.", row)

    action = "SHORT / ADD SOXS TOWARD TARGET"
    reason = "VIX is calm, QQQ is above MA20, and SOXS is not at a panic high."
    if qqq_rsi > 75:
        action = "HOLD / ADD SLOWLY"
        reason += " QQQ is short-term overbought, so scale rather than chase."
    return signal("normal", action, "medium", NORMAL_SHORT_ALLOC, reason, row)


def pct(x: float) -> str:
    return f"{x:.1%}"


def render_dashboard() -> None:
    st.title("SOXS Manual Signal")
    st.caption("Manual guide only. No broker connection. No order execution.")

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
    cols[1].metric("Target SOXS Short", pct(sig["target_short_alloc"]))
    cols[2].metric("VIX", f"{sig['vix']:.2f}")
    cols[3].metric("Confidence", sig["confidence"])

    cols = st.columns(4)
    cols[0].metric("QQQ", f"${sig['qqq']:.2f}")
    cols[1].metric("QQQ MA20", f"${sig['qqq_ma20']:.2f}")
    cols[2].metric("QQQ RSI14", f"{sig['qqq_rsi14']:.1f}")
    cols[3].metric("QQQ Below MA20", "Yes" if sig["qqq_below_ma20"] else "No")

    cols = st.columns(4)
    cols[0].metric("SOXS", f"${sig['soxs']:.2f}")
    cols[1].metric("SOXS MA5", f"${sig['soxs_ma5']:.2f}")
    cols[2].metric("SOXS 20D High", f"${sig['soxs_high20']:.2f}")
    cols[3].metric("SOXS Pullback", pct(sig["soxs_pullback_from_high20"]))

    st.divider()
    st.line_chart(df[["QQQ", "QQQ_MA20"]].tail(80))
    st.line_chart(df[["SOXS", "SOXS_MA5", "SOXS_MA20"]].tail(80))
    st.line_chart(df[["VIX"]].tail(80))

    st.subheader("Recent Data")
    st.dataframe(df.tail(20).round(2), use_container_width=True)

    st.download_button(
        "Download JSON signal",
        data=pd.Series(sig).to_json(indent=2),
        file_name="soxs_manual_signal.json",
        mime="application/json",
    )


if password_gate():
    try:
        render_dashboard()
    except Exception as exc:
        st.error(f"Could not generate signal: {exc}")

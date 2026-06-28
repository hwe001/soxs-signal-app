#!/usr/bin/env python3
"""
Streamlit QQQ Core / SQQQ Hedge-Overlay Manual Signal Dashboard.

Strategy:
- Core leg: long QQQ (buy-and-hold), trimmed defensively when QQQ loses its
  intermediate-term trend.
- Overlay leg: tactical short SQQQ, sized to harvest leveraged-ETF decay and
  add convexity to the long QQQ leg, gated by VIX regime, QQQ trend health,
  and SQQQ's own spike/fade behavior. Because SQQQ is QQQ's inverse, a sharp
  QQQ crash hurts both legs at once (correlated tail risk, not a diversified
  hedge), so the overlay is sized modestly and covered fast on the first
  sign of a squeeze rather than waiting on slower regime signals.

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
CAUTION_SHORT_ALLOC = 0.20
DANGER_SHORT_ALLOC = 0.10
EMERGENCY_SHORT_ALLOC = 0.00

VIX_CAUTION = 25.0
VIX_DANGER = 35.0
VIX_EMERGENCY = 45.0

SQQQ_SQUEEZE_RET3D = 0.12
SQQQ_SQUEEZE_RISE_FROM_LOW10 = 0.20
SQQQ_FADE_PULLBACK = -0.08
SQQQ_DECAYED_PULLBACK = -0.25

SQQQ_HIGH_LOOKBACK = 20
SQQQ_LOW_LOOKBACK = 10
QQQ_TREND_LOOKBACK = 50
QQQ_SOFT_LOOKBACK = 20
RSI_PERIOD = 14


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


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - 100 / (1 + rs)


def build_data() -> pd.DataFrame:
    qqq = fetch_history(CORE_SYMBOL)
    sqqq = fetch_history(SHORT_SYMBOL)
    vix = fetch_history(VIX_SYMBOL)
    df = pd.concat([qqq, sqqq, vix], axis=1, sort=True).ffill().dropna()
    df.columns = ["QQQ", "SQQQ", "VIX"]

    df["QQQ_MA20"] = df["QQQ"].rolling(QQQ_SOFT_LOOKBACK).mean()
    df["QQQ_MA50"] = df["QQQ"].rolling(QQQ_TREND_LOOKBACK).mean()
    df["QQQ_RSI14"] = rsi(df["QQQ"])

    df["SQQQ_MA5"] = df["SQQQ"].rolling(5).mean()
    df["SQQQ_MA20"] = df["SQQQ"].rolling(20).mean()
    df["SQQQ_HIGH5"] = df["SQQQ"].rolling(5).max()
    df["SQQQ_HIGH20"] = df["SQQQ"].rolling(SQQQ_HIGH_LOOKBACK).max()
    df["SQQQ_LOW10"] = df["SQQQ"].rolling(SQQQ_LOW_LOOKBACK).min()
    df["SQQQ_PULLBACK_FROM_HIGH20"] = df["SQQQ"] / df["SQQQ_HIGH20"] - 1.0
    df["SQQQ_RISE_FROM_LOW10"] = df["SQQQ"] / df["SQQQ_LOW10"] - 1.0
    df["SQQQ_RET3D"] = df["SQQQ"].pct_change(3)

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
        "qqq_ma20": float(row["QQQ_MA20"]),
        "qqq_ma50": float(row["QQQ_MA50"]),
        "qqq_rsi14": float(row["QQQ_RSI14"]),
        "qqq_below_ma20": bool(float(row["QQQ"]) < float(row["QQQ_MA20"])),
        "qqq_below_ma50": bool(float(row["QQQ"]) < float(row["QQQ_MA50"])),
        "sqqq": float(row["SQQQ"]),
        "sqqq_ma5": float(row["SQQQ_MA5"]),
        "sqqq_ma20": float(row["SQQQ_MA20"]),
        "sqqq_high5": float(row["SQQQ_HIGH5"]),
        "sqqq_high20": float(row["SQQQ_HIGH20"]),
        "sqqq_low10": float(row["SQQQ_LOW10"]),
        "sqqq_pullback_from_high20": float(row["SQQQ_PULLBACK_FROM_HIGH20"]),
        "sqqq_rise_from_low10": float(row["SQQQ_RISE_FROM_LOW10"]),
        "sqqq_ret3d": float(row["SQQQ_RET3D"]),
        "sqqq_at_high20": bool(float(row["SQQQ"]) >= float(row["SQQQ_HIGH20"]) * 0.98),
        "vix": float(row["VIX"]),
    }


def classify_core(row: pd.Series) -> tuple[str, float]:
    if float(row["QQQ"]) < float(row["QQQ_MA50"]):
        return "TRIM CORE QQQ TOWARD DEFENSIVE WEIGHT", CORE_DEFENSIVE_ALLOC
    return "HOLD FULL CORE QQQ", CORE_FULL_ALLOC


def classify_signal(row: pd.Series) -> dict:
    vix = float(row["VIX"])
    qqq = float(row["QQQ"])
    qqq_ma20 = float(row["QQQ_MA20"])
    qqq_rsi = float(row["QQQ_RSI14"])
    sqqq = float(row["SQQQ"])
    sqqq_ma5 = float(row["SQQQ_MA5"])
    sqqq_high5 = float(row["SQQQ_HIGH5"])
    sqqq_high20 = float(row["SQQQ_HIGH20"])
    sqqq_pullback = float(row["SQQQ_PULLBACK_FROM_HIGH20"])
    sqqq_rise_from_low10 = float(row["SQQQ_RISE_FROM_LOW10"])
    sqqq_ret3d = float(row["SQQQ_RET3D"])

    # A 20-day high touched within the last week is treated as a live "spike"
    # even after today's price has pulled back off that peak.
    sqqq_recent_spike = sqqq_high5 >= sqqq_high20 * 0.98
    sqqq_still_at_peak = sqqq_pullback >= -0.02
    qqq_below_ma20 = qqq < qqq_ma20
    sqqq_fading = sqqq < sqqq_ma5 and sqqq_pullback <= SQQQ_FADE_PULLBACK

    core_action, core_alloc = classify_core(row)

    # Fast safety valve: cover before slower regime signals (VIX, trend) can react.
    if sqqq_ret3d >= SQQQ_SQUEEZE_RET3D or sqqq_rise_from_low10 >= SQQQ_SQUEEZE_RISE_FROM_LOW10:
        return signal(
            "sqqq_squeeze", core_action, core_alloc,
            "COVER SQQQ SHORT IMMEDIATELY", EMERGENCY_SHORT_ALLOC, "high",
            "SQQQ is surging fast; cover the overlay now to avoid squeeze losses.", row,
        )

    if vix >= VIX_EMERGENCY:
        return signal(
            "emergency", core_action, core_alloc,
            "COVER / FLATTEN SQQQ SHORT", EMERGENCY_SHORT_ALLOC, "high",
            "VIX is in crisis territory; the inverse-ETF short overlay is too dangerous to hold.", row,
        )
    if vix >= VIX_DANGER:
        return signal(
            "danger", core_action, core_alloc,
            "REDUCE SQQQ SHORT / DO NOT ADD", DANGER_SHORT_ALLOC, "high",
            "VIX is very elevated; cut the overlay and do not add into panic.", row,
        )
    if vix >= VIX_CAUTION:
        return signal(
            "caution", core_action, core_alloc,
            "HOLD SMALL SQQQ SHORT OR REDUCE; DO NOT ADD", CAUTION_SHORT_ALLOC, "medium",
            "VIX is elevated; wait for clearer panic fade before sizing the overlay back up.", row,
        )
    if qqq_below_ma20:
        return signal(
            "qqq_soft", core_action, core_alloc,
            "HOLD OR REDUCE SQQQ SHORT; DO NOT ADD", CAUTION_SHORT_ALLOC, "medium",
            "QQQ is below its 20-day moving average; SQQQ tends to rally here, so don't add to the short.", row,
        )
    if sqqq_recent_spike:
        if sqqq_still_at_peak:
            return signal(
                "sqqq_spike", core_action, core_alloc,
                "WAIT; DO NOT SHORT A VERTICAL SQQQ SPIKE", CAUTION_SHORT_ALLOC, "high",
                "SQQQ is at its 20-day high right now; wait for pullback confirmation before adding.", row,
            )
        if sqqq_fading:
            return signal(
                "sqqq_spike_fade", core_action, core_alloc,
                "START / ADD SMALL SQQQ SHORT", CAUTION_SHORT_ALLOC, "medium",
                "SQQQ spiked this week and is now rolling over while QQQ holds its trend; fade the spike in small size.", row,
            )
        return signal(
            "sqqq_spike_cooling", core_action, core_alloc,
            "WAIT; CONFIRM FADE BEFORE ADDING", CAUTION_SHORT_ALLOC, "medium",
            "SQQQ is off its recent high but hasn't confirmed a fade yet; hold off on new adds.", row,
        )
    if sqqq_pullback <= SQQQ_DECAYED_PULLBACK:
        return signal(
            "sqqq_decayed", core_action, core_alloc,
            "TRIM SQQQ SHORT TOWARD SMALLER SIZE", CAUTION_SHORT_ALLOC, "medium",
            "SQQQ has already decayed well off its recent high; harvest gains and reduce bounce risk.", row,
        )

    action = "SHORT / ADD SQQQ TOWARD TARGET"
    reason = "VIX is calm, QQQ is above its trend, and SQQQ is not at a panic high."
    if qqq_rsi > 75:
        action = "HOLD / ADD SLOWLY"
        reason += " QQQ is short-term overbought, so scale in rather than chase."
    return signal("normal", core_action, core_alloc, action, NORMAL_SHORT_ALLOC, "medium", reason, row)


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
    cols[0].metric("VIX", f"{sig['vix']:.2f}")
    cols[1].metric("QQQ", f"${sig['qqq']:.2f}")
    cols[2].metric("QQQ MA20", f"${sig['qqq_ma20']:.2f}")
    cols[3].metric("QQQ MA50", f"${sig['qqq_ma50']:.2f}")

    cols = st.columns(4)
    cols[0].metric("QQQ RSI14", f"{sig['qqq_rsi14']:.1f}")
    cols[1].metric("SQQQ", f"${sig['sqqq']:.2f}")
    cols[2].metric("SQQQ MA5", f"${sig['sqqq_ma5']:.2f}")
    cols[3].metric("SQQQ 20D High", f"${sig['sqqq_high20']:.2f}")

    cols = st.columns(4)
    cols[0].metric("SQQQ Pullback From High20", pct(sig["sqqq_pullback_from_high20"]))
    cols[1].metric("SQQQ Rise From Low10", pct(sig["sqqq_rise_from_low10"]))
    cols[2].metric("SQQQ 3D Return", pct(sig["sqqq_ret3d"]))
    cols[3].metric("QQQ Below MA50", "Yes" if sig["qqq_below_ma50"] else "No")

    st.divider()
    st.line_chart(df[["QQQ", "QQQ_MA20", "QQQ_MA50"]].tail(120))
    st.line_chart(df[["SQQQ", "SQQQ_MA5", "SQQQ_MA20"]].tail(120))
    st.line_chart(df[["VIX"]].tail(120))

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

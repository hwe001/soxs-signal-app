#!/usr/bin/env python3
"""
Shared signal logic for the QQQ core + short SOXS overlay strategy.

Pure functions only -- no Streamlit, no data fetching, no broker calls --
so this can be imported by both the read-only dashboard
(streamlit_soxs_core_app.py) and the paper-trading runner
(paper_trade_runner.py) without triggering either one's side effects.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


CORE_SYMBOL = "QQQ"
SHORT_SYMBOL = "SOXS"
VIX_SYMBOL = "^VIX"

CORE_ALLOC = 0.40

NORMAL_SHORT_ALLOC = 0.60
TREND_BROKEN_SHORT_ALLOC = 0.15

QQQ_TREND_LOOKBACK = 50


def signal(
    regime: str,
    overlay_action: str,
    short_alloc: float,
    confidence: str,
    reason: str,
    row: pd.Series,
) -> dict:
    cash_alloc = 1.0 - CORE_ALLOC - short_alloc
    return {
        "timestamp_ny": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "core_action": "HOLD CORE QQQ",
        "core_target_alloc": CORE_ALLOC,
        "overlay_action": overlay_action,
        "overlay_target_short_alloc": short_alloc,
        "target_cash_alloc": cash_alloc,
        "confidence": confidence,
        "reason": reason,
        "qqq": float(row["QQQ"]),
        "qqq_ma50": float(row["QQQ_MA50"]),
        "qqq_below_ma50": bool(float(row["QQQ"]) < float(row["QQQ_MA50"])),
        "soxs": float(row["SOXS"]),
    }


def classify_signal(row: pd.Series) -> dict:
    qqq_below_ma50 = float(row["QQQ"]) < float(row["QQQ_MA50"])

    if qqq_below_ma50:
        return signal(
            "trend_broken", "REDUCE SOXS SHORT TOWARD FLOOR", TREND_BROKEN_SHORT_ALLOC, "high",
            "QQQ is below its 50-day trend; cut the short SOXS overlay back to a 15% floor "
            "rather than fully covering it. The 40% QQQ core is held unchanged.", row,
        )
    return signal(
        "normal", "HOLD / ADD SOXS SHORT TOWARD TARGET", NORMAL_SHORT_ALLOC, "medium",
        "QQQ is above its 50-day trend; hold the full 60% short SOXS overlay to harvest "
        "leveraged-ETF decay alongside the 40% QQQ core.", row,
    )

#!/usr/bin/env python3
"""
Shared signal logic for the QQQ core + short SQQQ hedge-overlay strategy.

Pure functions only: no Streamlit, no data fetching, no broker calls.
The constants and classification logic mirror streamlit_qqq_sqqq_app.py.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


CORE_SYMBOL = "QQQ"
SHORT_SYMBOL = "SQQQ"
VIX_SYMBOL = "^VIX"

CORE_FULL_ALLOC = 1.00
CORE_DEFENSIVE_ALLOC = 0.75

NORMAL_SHORT_ALLOC = 0.40
TREND_BROKEN_SHORT_ALLOC = 0.20

QQQ_TREND_LOOKBACK = 50


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
        "target_cash_alloc": 1.0 - core_alloc - overlay_alloc,
        "confidence": confidence,
        "reason": reason,
        "qqq": float(row["QQQ"]),
        "qqq_ma50": float(row["QQQ_MA50"]),
        "qqq_below_ma50": bool(float(row["QQQ"]) < float(row["QQQ_MA50"])),
        "sqqq": float(row["SQQQ"]),
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
            "trend_broken",
            core_action,
            core_alloc,
            "REDUCE SQQQ SHORT TOWARD FLOOR",
            TREND_BROKEN_SHORT_ALLOC,
            "high",
            "QQQ is below its 50-day trend; cut the short overlay back to a 20% floor "
            "position rather than fully covering it.",
            row,
        )
    return signal(
        "normal",
        core_action,
        core_alloc,
        "HOLD / ADD SQQQ SHORT TOWARD TARGET",
        NORMAL_SHORT_ALLOC,
        "medium",
        "QQQ is above its 50-day trend; hold the full short SQQQ overlay to harvest "
        "leveraged-ETF decay alongside the long core.",
        row,
    )

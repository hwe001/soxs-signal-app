#!/usr/bin/env python3
"""
Shared signal logic for the QQQ core + short SOXS overlay strategy.

Pure functions only: no Streamlit, no data fetching, no broker calls.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


CORE_SYMBOL = "QQQ"
SHORT_SYMBOL = "SOXS"
VIX_SYMBOL = "^VIX"

CORE_ALLOC = 0.40

SHORT_ALLOC = 0.60

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
        "soxs": float(row["SOXS"]),
    }


def classify_core(row: pd.Series) -> tuple[str, float]:
    return "HOLD CORE QQQ", CORE_ALLOC


def classify_signal(row: pd.Series) -> dict:
    qqq_below_ma50 = float(row["QQQ"]) < float(row["QQQ_MA50"])
    core_action, core_alloc = classify_core(row)

    if qqq_below_ma50:
        return signal(
            "trend_broken",
            core_action,
            core_alloc,
            "HOLD 60% SOXS SHORT TARGET",
            SHORT_ALLOC,
            "high",
            "QQQ is below its 50-day trend, but this comparison variant keeps the "
            "40% QQQ core and 60% short SOXS target unchanged.",
            row,
        )
    return signal(
        "normal",
        core_action,
        core_alloc,
        "HOLD / ADD SOXS SHORT TOWARD TARGET",
        SHORT_ALLOC,
        "medium",
        "QQQ is above its 50-day trend; hold the full 60% short SOXS overlay to harvest "
        "leveraged-ETF decay alongside the 40% QQQ core.",
        row,
    )

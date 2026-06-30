#!/usr/bin/env python3
"""
HIVE equity + HIVE options advisory + QQQ long-term core strategy.

Pure functions only: no Streamlit, no data fetching, no broker calls.

Strategy thesis:
- QQQ (50%) is the long-term wealth compounder — always held, rarely trimmed.
- HIVE equity (0-30%) captures Bitcoin mining + AI theme beta; sized by BTC trend.
- HIVE options overlay (advisory) harvests elevated IV premium to offset QQQ cost basis.
- BTC 20-day MA is the primary HIVE on/off switch; QQQ 50-day MA and VIX apply risk scaling.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


QQQ_SYMBOL = "QQQ"
HIVE_SYMBOL = "HIVE"
BTC_SYMBOL = "BTC-USD"
VIX_SYMBOL = "^VIX"

# Core allocation targets
QQQ_BASE_ALLOC = 0.50
QQQ_REDUCED_ALLOC = 0.40   # danger / risk-off
QQQ_BOOSTED_ALLOC = 0.60   # calm market, VIX < 15

HIVE_BULL_ALLOC = 0.30      # BTC trend up, QQQ healthy, VIX calm
HIVE_CAUTION_ALLOC = 0.15   # mixed signals
HIVE_FLAT_ALLOC = 0.00      # BTC bear or high VIX

# Technical lookbacks (trading days)
QQQ_TREND_LOOKBACK = 50
BTC_TREND_LOOKBACK = 20
HIVE_LOOKBACK = 20

# VIX thresholds
VIX_CALM = 15.0
VIX_CAUTION = 30.0
VIX_DANGER = 40.0


def _classify_regime(btc_above_ma: bool, qqq_above_ma50: bool, vix: float) -> str:
    if vix >= VIX_DANGER:
        return "danger"
    if not btc_above_ma and vix >= VIX_CAUTION:
        return "btc_bear_vix_elevated"
    if not btc_above_ma:
        return "btc_bear"
    if btc_above_ma and qqq_above_ma50 and vix < VIX_CAUTION:
        return "bull"
    if btc_above_ma and not qqq_above_ma50:
        return "btc_bull_qqq_soft"
    return "caution"


def _options_advisory(regime: str, hive_alloc: float, hive_above_ma20: bool, vix: float) -> dict:
    """Returns an advisory options overlay recommendation (not executed by paper runner)."""
    if hive_alloc == 0 or regime == "danger":
        return {
            "action": "NO OPTIONS — HIVE FLAT",
            "detail": "No HIVE position. No covered calls available. Wait for BTC trend to recover.",
        }
    if hive_above_ma20 and vix > 20:
        return {
            "action": "SELL COVERED CALLS",
            "detail": (
                "HIVE is above its 20-day MA with elevated IV. "
                "Sell calls 15-20% OTM, ~30 DTE to harvest premium. "
                "Roll up-and-out if HIVE rallies through the strike. "
                "Use collected premium to reduce QQQ effective cost basis."
            ),
        }
    if not hive_above_ma20 and regime in ("caution", "btc_bull_qqq_soft"):
        return {
            "action": "SELL CASH-SECURED PUTS (OPTIONAL)",
            "detail": (
                "HIVE has pulled back while BTC trend is intact. "
                "Consider selling puts 15-20% OTM, ~30 DTE for premium and a better HIVE entry. "
                "Only if put premium exceeds 3% of the strike price."
            ),
        }
    return {
        "action": "HOLD — NO NEW OPTIONS",
        "detail": "Conditions are not ideal for new option legs. Manage or let existing positions decay.",
    }


def _signal(
    regime: str,
    qqq_action: str,
    qqq_alloc: float,
    hive_action: str,
    hive_alloc: float,
    options: dict,
    confidence: str,
    reason: str,
    row: pd.Series,
) -> dict:
    return {
        "timestamp_ny": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime,
        "qqq_action": qqq_action,
        "qqq_target_alloc": qqq_alloc,
        "hive_action": hive_action,
        "hive_target_alloc": hive_alloc,
        "target_cash_alloc": max(0.0, 1.0 - qqq_alloc - hive_alloc),
        "options_action": options["action"],
        "options_detail": options["detail"],
        "confidence": confidence,
        "reason": reason,
        "qqq": float(row["QQQ"]),
        "qqq_ma50": float(row["QQQ_MA50"]),
        "qqq_above_ma50": float(row["QQQ"]) >= float(row["QQQ_MA50"]),
        "hive": float(row["HIVE"]),
        "hive_ma20": float(row["HIVE_MA20"]),
        "hive_above_ma20": float(row["HIVE"]) >= float(row["HIVE_MA20"]),
        "btc": float(row["BTC"]),
        "btc_ma20": float(row["BTC_MA20"]),
        "btc_above_ma20": float(row["BTC"]) >= float(row["BTC_MA20"]),
        "vix": float(row["VIX"]),
    }


def classify_signal(row: pd.Series) -> dict:
    """
    Classify the current market regime and return a combined HIVE + QQQ signal.

    Expected row columns:
        QQQ, QQQ_MA50, HIVE, HIVE_MA20, BTC, BTC_MA20, VIX
    """
    vix = float(row["VIX"])
    btc_above_ma20 = float(row["BTC"]) >= float(row["BTC_MA20"])
    qqq_above_ma50 = float(row["QQQ"]) >= float(row["QQQ_MA50"])
    hive_above_ma20 = float(row["HIVE"]) >= float(row["HIVE_MA20"])

    regime = _classify_regime(btc_above_ma20, qqq_above_ma50, vix)

    if regime == "danger":
        opts = _options_advisory(regime, HIVE_FLAT_ALLOC, hive_above_ma20, vix)
        return _signal(
            regime,
            "HOLD QQQ — DO NOT ADD", QQQ_REDUCED_ALLOC,
            "EXIT HIVE — GO FLAT", HIVE_FLAT_ALLOC,
            opts,
            "high",
            f"VIX {vix:.1f} is above {VIX_DANGER}: risk-off. Exit HIVE, hold reduced QQQ core, raise cash.",
            row,
        )

    if regime == "btc_bear_vix_elevated":
        opts = _options_advisory(regime, HIVE_FLAT_ALLOC, hive_above_ma20, vix)
        return _signal(
            regime,
            "HOLD QQQ CORE", QQQ_BASE_ALLOC,
            "NO HIVE — BTC BEAR + VIX ELEVATED", HIVE_FLAT_ALLOC,
            opts,
            "high",
            "BTC below 20-day MA and VIX elevated: HIVE has no tailwind and tail risk is elevated. "
            "Skip HIVE until BTC trend recovers.",
            row,
        )

    if regime == "btc_bear":
        opts = _options_advisory(regime, HIVE_FLAT_ALLOC, hive_above_ma20, vix)
        return _signal(
            regime,
            "HOLD QQQ CORE", QQQ_BASE_ALLOC,
            "NO HIVE — AWAIT BTC TREND", HIVE_FLAT_ALLOC,
            opts,
            "medium",
            "BTC is below its 20-day MA: HIVE has no Bitcoin tailwind. "
            "Hold QQQ; wait for BTC to reclaim its trend before adding HIVE.",
            row,
        )

    if regime == "btc_bull_qqq_soft":
        opts = _options_advisory(regime, HIVE_CAUTION_ALLOC, hive_above_ma20, vix)
        return _signal(
            regime,
            "HOLD QQQ CORE — DO NOT ADD", QQQ_BASE_ALLOC,
            "SMALL HIVE POSITION ONLY", HIVE_CAUTION_ALLOC,
            opts,
            "medium",
            "BTC trend is intact but QQQ is below its 50-day MA: hold a small HIVE position "
            "and wait for QQQ to reclaim its trend before adding.",
            row,
        )

    if regime == "caution":
        opts = _options_advisory(regime, HIVE_CAUTION_ALLOC, hive_above_ma20, vix)
        return _signal(
            regime,
            "HOLD QQQ CORE", QQQ_BASE_ALLOC,
            "HOLD / REDUCE HIVE", HIVE_CAUTION_ALLOC,
            opts,
            "medium",
            f"Mixed signals (VIX {vix:.1f}): maintain a small HIVE position, hold QQQ core.",
            row,
        )

    # Bull regime: BTC above MA20, QQQ above MA50, VIX < VIX_CAUTION
    qqq_alloc = QQQ_BOOSTED_ALLOC if vix < VIX_CALM else QQQ_BASE_ALLOC
    hive_alloc = HIVE_BULL_ALLOC
    opts = _options_advisory(regime, hive_alloc, hive_above_ma20, vix)
    qqq_action = "ADD TO QQQ — CALM MARKET BOOST" if qqq_alloc > QQQ_BASE_ALLOC else "HOLD QQQ CORE"
    return _signal(
        regime,
        qqq_action, qqq_alloc,
        "BUY / HOLD HIVE — FULL BULL ALLOCATION", hive_alloc,
        opts,
        "medium",
        f"BTC above MA20, QQQ above MA50, VIX {vix:.1f}: deploy full HIVE position and "
        "harvest covered call premium to offset QQQ cost basis over time.",
        row,
    )

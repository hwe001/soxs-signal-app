# Signal Dashboards

Public Streamlit dashboards for manual trading signal checks.

All apps:

- Pull public market data from Yahoo Finance.
- Show a manual signal for entry/cover decisions.
- Do not connect to Alpaca.
- Do not place trades.
- Do not contain broker keys.

## Apps

### SOXS Signal (`streamlit_signal_app.py`)

Uses QQQ trend health and VIX regime to gate a tactical short SOXS overlay.

### QQQ Core + SQQQ Hedge Overlay (`streamlit_qqq_sqqq_app.py`)

Core leg: long QQQ, trimmed defensively to 75% when QQQ loses its 50-day
trend.

Overlay leg: short SQQQ at a fixed 40% weight whenever QQQ is above its
50-day MA, cut back to a 20% floor (not fully covered) when the trend
breaks.

A 10-year backtest (2016-2026) compared this against a much more elaborate
version with VIX-regime bands, a fast squeeze valve, spike/fade entry
timing, an RSI throttle, and a decay-harvest trim. The extra complexity
didn't improve risk-adjusted returns over the single 50-day trend filter —
a fast reactive squeeze valve was actively harmful on its own, causing
whipsaw losses by covering and immediately re-shorting at worse levels
during the 2022 grinding bear market. VIX is still fetched and shown for
context but does not drive the signal.

The floor size is a direct risk/return dial: over the backtest window,
a 0% floor (full cover) gives 34.1% CAGR / -43.2% max drawdown / 0.79
Calmar; a 20% floor (current setting) gives 36.9% CAGR / -54.0% max
drawdown / 0.68 Calmar. Buy-and-hold QQQ is 21.9% CAGR / -35.1% max
drawdown / 0.62 Calmar for reference. At the 20% floor, Sharpe (1.00)
is roughly tied with buy-and-hold (1.00) and the 2022 grinding bear
market would have cost -50.1% vs. buy-and-hold's -32.6% — higher
absolute return, but the risk-adjusted edge over plain buy-and-hold is
thin at this floor size.

### Cash + Short SOXS Core (`streamlit_soxs_core_app.py`)

No QQQ is ever held. QQQ's 50-day trend is used purely as an external
signal: short SOXS at a fixed 60% weight whenever QQQ is above its 50-day
MA, cut back to a 15% floor (not fully covered) when the trend breaks. The
rest of the book sits in cash.

Short-side dividends: prices are dividend-adjusted (Yahoo's adjusted
close), so `-pct_change(adjusted_close)` already nets the ex-distribution
price-drop benefit against the payment-in-lieu-of-dividend owed to the
share lender. No separate dividend adjustment is needed; the stock-loan
borrow fee is a distinct, separately modeled cost.

This is a simplified, capital-efficient sibling of `streamlit_signal_app.py`
(the original VIX-band + spike/fade + RSI-throttle SOXS logic). Backtested
over the same 2016-2026 window:

| Strategy | CAGR | Max DD | Sharpe | Calmar |
|---|---|---|---|---|
| Original elaborate SOXS logic (VIX bands + spike/fade + RSI) | 33.4% | -47.9% | 0.95 | 0.70 |
| Simplified 40%/15% trend-filter | 29.1% | -40.6% | 0.98 | 0.72 |
| Simplified 60%/15% trend-filter (this app) | 38.7% | -53.4% | 0.96 | 0.72 |
| Buy & hold QQQ (reference) | 21.6% | -35.1% | 0.99 | 0.61 |

Sizing is a pure risk/return dial here, not a free upgrade: 60%/15% matches
the 40%/15% Calmar (0.72) at a notably higher CAGR, but the max drawdown
is deeper than even the original elaborate logic's (-53.4% vs -47.9%).

## Streamlit Secrets

Add this app secret in Streamlit Cloud:

```toml
SIGNAL_APP_PASSWORD = "your-password"
```

## Main Files

```text
streamlit_signal_app.py
streamlit_qqq_sqqq_app.py
streamlit_soxs_core_app.py
```

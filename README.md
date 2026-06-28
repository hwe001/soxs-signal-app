# Signal Dashboards

Public Streamlit dashboards for manual trading signal checks.

Both apps:

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

## Streamlit Secrets

Add this app secret in Streamlit Cloud:

```toml
SIGNAL_APP_PASSWORD = "your-password"
```

## Main Files

```text
streamlit_signal_app.py
streamlit_qqq_sqqq_app.py
```

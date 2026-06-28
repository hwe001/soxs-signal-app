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
50-day MA, cut back to a 5% floor (not fully covered) when the trend
breaks.

A 10-year backtest (2016-2026) compared this against a much more elaborate
version with VIX-regime bands, a fast squeeze valve, spike/fade entry
timing, an RSI throttle, and a decay-harvest trim. The extra complexity
didn't improve risk-adjusted returns over the single 50-day trend filter —
a fast reactive squeeze valve was actively harmful on its own, causing
whipsaw losses by covering and immediately re-shorting at worse levels
during the 2022 grinding bear market. The simple version above beat
buy-and-hold QQQ on CAGR, Sharpe, and Calmar over the backtest window
(34.9% CAGR / -45.9% max drawdown vs. 21.9% CAGR / -35.1% max drawdown for
buy-and-hold), so the dashboard implements that version. VIX is still
fetched and shown for context but does not drive the signal.

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

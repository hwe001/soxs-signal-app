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

Core leg: long QQQ, trimmed defensively when QQQ loses its 50-day trend.

Overlay leg: tactical short SQQQ, sized 0-40% of portfolio. Because SQQQ is
QQQ's inverse, a sharp QQQ crash hurts the long core and the short overlay
at the same time (correlated tail risk, not a diversified hedge), so the
overlay is sized modestly and gated by several independent signals:

- **Fast squeeze valve** (checked first): cover immediately if SQQQ surges
  12%+ in 3 days, or is 20%+ above its 10-day low, regardless of VIX.
- **VIX regime**: shrinks the max overlay size as fear rises (calm → caution
  → danger → emergency), with no new adds above calm.
- **QQQ trend filter**: never add to the short while QQQ is below its
  20-day MA, since SQQQ tends to rally exactly then.
- **Spike/fade entry**: don't chase a fresh SQQQ high; only add into a
  confirmed fade (rolling over below its 5-day MA after pulling back from
  a high touched in the last week) while QQQ stays healthy.
- **Profit harvest**: trims the overlay once SQQQ has decayed 25%+ off its
  recent high, since most of the easy decay is captured and bounce risk
  rises.

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

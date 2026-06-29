# Signal Dashboard

Public Streamlit dashboard for manual signal checks, with two tabs:

- **SOXS Hedge** — manual signal for SOXS short/cover decisions, sized off QQQ trend and VIX.
- **HIVE / SPY Core-Satellite** — a long-term SPY core (buy-and-hold, DCA on dips, never sell)
  paired with an actively-traded HIVE satellite position sized off the Bitcoin trend and VIX.

This app:

- Pulls public market data from Yahoo Finance.
- Shows manual signals only; it does not give personalized financial advice.
- Does not connect to Alpaca.
- Does not place trades.
- Does not contain broker keys.

## Streamlit Secrets

Add this app secret in Streamlit Cloud:

```toml
SIGNAL_APP_PASSWORD = "your-password"
```

Optional weekly Claude brief:

```toml
ANTHROPIC_API_KEY = "your-anthropic-api-key"
CLAUDE_MODEL = "claude-haiku-4-5"
```

Weekly briefs are generated only when you press the button in the app.
The SOXS tab brief passes recent public AI, semiconductor, and mega-cap headlines for QQQ trend
context. The HIVE/SPY tab brief passes recent HIVE and Bitcoin-mining headlines for BTC trend
context.

## Main File

```text
streamlit_signal_app.py
```

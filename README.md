# SOXS Signal Dashboard

Public Streamlit dashboard for manual SOXS signal checks.

This app:

- Pulls public market data from Yahoo Finance.
- Shows a manual signal for SOXS short/cover decisions.
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

The weekly brief is generated only when you press the button in the app.
It also passes recent public AI, semiconductor, and mega-cap headlines into the prompt for QQQ trend context.

## Main File

```text
streamlit_signal_app.py
```

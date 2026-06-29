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

## QQQ/SQQQ Paper Bot

This repo also contains a separate Alpaca paper-trading runner for the
QQQ core + short SQQQ hedge-overlay strategy from the
`claude/qqq-sqqq-hedge-strategy-gv868s` branch.

It uses separate GitHub Actions secrets from the SOXS bot:

```toml
SQQQ_ALPACA_API_KEY_ID = "your-separate-paper-key-id"
SQQQ_ALPACA_API_SECRET_KEY = "your-separate-paper-secret-key"
SQQQ_EXECUTE_ORDERS = "false"
```

Set `SQQQ_EXECUTE_ORDERS` to `"true"` only when scheduled workflow runs
should submit Alpaca paper orders. The manual workflow can also be run as a
dry run first.

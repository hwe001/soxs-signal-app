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

## QQQ/SOXS Core Paper Bot

This repo also contains a separate Alpaca paper-trading runner for a
QQQ core + short SOXS strategy.

It uses separate GitHub Actions secrets from the SOXS bot:

```toml
SOXS_CORE_ALPACA_API_KEY_ID = "your-separate-paper-key-id"
SOXS_CORE_ALPACA_API_SECRET_KEY = "your-separate-paper-secret-key"
SOXS_CORE_EXECUTE_ORDERS = "false"
```

The target is fixed at 40% long QQQ plus 60% short SOXS. The bot still
reports whether QQQ is above or below its 50-day moving average, but this
comparison variant does not change target weights based on that filter.

For backward compatibility, the older `SQQQ_ALPACA_*` and
`SQQQ_EXECUTE_ORDERS` secrets still work. Set `SOXS_CORE_EXECUTE_ORDERS` to
`"true"` only when scheduled workflow runs should submit Alpaca paper orders.
The manual workflow can also be run as a dry run first.

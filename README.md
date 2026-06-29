# Signal Dashboards

Public Streamlit dashboards for manual trading signal checks, plus one
opt-in paper-trading execution script.

The three Streamlit apps:

- Pull public market data from Yahoo Finance.
- Show a manual signal for entry/cover decisions.
- Do not connect to Alpaca.
- Do not place trades.
- Do not contain broker keys.

`paper_trade_runner.py` is the exception: it connects to Alpaca's PAPER
trading API only and places orders to rebalance to the
`streamlit_soxs_core_app.py` signal. See that section below.

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

### QQQ/SQQQ Paper Bot (`qqq_sqqq_paper_trade_runner.py`)

Connects to Alpaca's **paper** trading API only and rebalances to the
QQQ/SQQQ dashboard signal:

- QQQ core: 100% when QQQ is above its 50-day MA, 75% when below.
- SQQQ short overlay: 40% when QQQ is above its 50-day MA, 20% floor when below.
- The strategy logic is intentionally kept the same as the dashboard so this
  can be compared cleanly against other bots.

This bot uses separate GitHub Actions secrets from the SOXS bot:

```toml
SQQQ_ALPACA_API_KEY_ID = "your-separate-paper-key-id"
SQQQ_ALPACA_API_SECRET_KEY = "your-separate-paper-secret-key"
SQQQ_EXECUTE_ORDERS = "false"
```

Set `SQQQ_EXECUTE_ORDERS` to `"true"` only when you want scheduled workflow
runs to submit Alpaca paper orders. Manual workflow runs can also choose
whether to submit paper orders and whether to bypass the 3:45 PM New York
time gate for testing.

### QQQ Core + Short SOXS Overlay (`streamlit_soxs_core_app.py`)

Core leg: long QQQ at a fixed 40% weight, held regardless of regime.

Overlay leg: short SOXS at a fixed 60% weight whenever QQQ is above its
50-day MA, cut back to a 15% floor (not fully covered) when the trend
breaks. The remainder of NAV (40-45% depending on regime) sits in cash.

Short-side dividends: prices are dividend-adjusted (Yahoo's adjusted
close), so `-pct_change(adjusted_close)` already nets the ex-distribution
price-drop benefit against the payment-in-lieu-of-dividend owed to the
share lender. No separate dividend adjustment is needed; the stock-loan
borrow fee is a distinct, separately modeled cost.

This is a simplified sibling of `streamlit_signal_app.py` (the original
VIX-band + spike/fade + RSI-throttle SOXS logic). Backtested over the same
2016-2026 window:

| Strategy | CAGR | Max DD | Sharpe | Calmar |
|---|---|---|---|---|
| Original elaborate SOXS logic (VIX bands + spike/fade + RSI) | 33.4% | -47.9% | 0.95 | 0.70 |
| Cash + 40%/15% SOXS-only trend-filter | 29.1% | -40.6% | 0.98 | 0.72 |
| Cash + 60%/15% SOXS-only trend-filter | 38.7% | -53.4% | 0.96 | 0.72 |
| 40% QQQ core + 60%/15% SOXS overlay (this app) | 46.7% | -57.7% | 1.01 | 0.81 |
| Buy & hold QQQ (reference) | 21.6% | -35.1% | 0.99 | 0.61 |

Adding the 40% QQQ core to the 60%/15% SOXS overlay isn't just added
leverage — it improves Sharpe and Calmar over the SOXS-only version
(1.01/0.81 vs 0.96/0.72) because long QQQ and short SOXS aren't perfectly
correlated (broad market vs. semiconductor-sector decay). It still raises
CAGR and deepens the max drawdown beyond the original elaborate logic's,
so this remains a higher-risk configuration overall, not a strict
improvement on every axis.

## Paper Trading Runner (`paper_trade_runner.py`)

Connects to Alpaca's **paper** trading API only and rebalances the account
to the exact signal from `streamlit_soxs_core_app.py` / `soxs_core_strategy.py`:
40% long QQQ (fixed) plus short SOXS at 60% (normal) or 15% (QQQ below its
50-day MA), sized in whole shares.

- Refuses to run if the connected account isn't a paper account.
- Refuses to run if SOXS isn't currently shortable/easy-to-borrow.
- Defaults to a dry run that only prints the orders it would place — pass
  `--execute` to actually submit them.
- Rebalances fully to target weights on every run; intended to be run once
  per trading day (e.g. via cron).

```bash
python paper_trade_runner.py            # dry run, prints intended orders
python paper_trade_runner.py --execute  # places the orders
```

Add your Alpaca **paper** keys (not live keys) to `.streamlit/secrets.toml`
(already gitignored):

```toml
ALPACA_API_KEY_ID = "your-paper-key-id"
ALPACA_API_SECRET_KEY = "your-paper-secret-key"
```

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
soxs_core_strategy.py
paper_trade_runner.py
```

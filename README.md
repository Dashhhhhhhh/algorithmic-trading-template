# Bare-Bones Algorithmic Trading Boilerplate (Python)

Minimal, beginner-friendly starter for a student club.  
This project runs one end-to-end pass:
1. Fetch live market data from Alpaca
2. Generate a toy signal (`sma_crossover` or `hft_pulse`)
3. Send market orders to Alpaca (or simulate in dry run)
4. Log each step clearly
5. Repeat continuously like a live bot (unless `--once` is used)

## Project Structure

```text
.
├── .env.example
├── README.md
├── requirements.txt
├── app
│   ├── __init__.py
│   ├── config.py
│   ├── backtest.py
│   ├── logging_utils.py
│   ├── main.py
│   ├── broker
│   │   ├── __init__.py
│   │   ├── alpaca.py
│   │   └── models.py
│   ├── data
│   │   ├── __init__.py
│   │   ├── alpaca_data.py
│   │   ├── base.py
│   │   ├── csv_data.py
│   │   └── models.py
│   ├── execution
│   │   ├── __init__.py
│   │   └── trader.py
│   ├── strategy
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── hft_pulse.py
│   │   └── sma_crossover.py
│   └── utils
│       ├── __init__.py
│       ├── errors.py
│       └── time.py
└── tests
    ├── test_backtest.py
    ├── test_cli_overrides.py
    ├── test_csv_data.py
    ├── test_hft_pulse.py
    ├── test_runtime_validation.py
    ├── test_trader_open_orders.py
    ├── test_trader_order_logic.py
    └── test_sma_crossover.py
```

## Requirements

- Python 3.11+
- Alpaca account + API keys (paper account recommended)

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy and edit:

```bash
cp .env.example .env
```

Required variables by mode:
- Live/paper trading mode: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
- CSV backtest mode: no API key is required

Key defaults:
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `ALPACA_DATA_URL=https://data.alpaca.markets`
- `SYMBOLS=SPY`
- `DATA_SOURCE=alpaca`
- `HISTORICAL_DATA_DIR=historical_data`
- `STRATEGY=sma_crossover`
- `DRY_RUN=true`
- `ALLOW_SHORT=true`
- `ORDER_QTY=1`
- `LOOP_INTERVAL_SECONDS=30`
- `BACKTEST_STARTING_CASH=100000`

## Run

Run continuously (live bot behavior):

```bash
python -m app.main --strategy hft_pulse --symbols SPY --qty 1 --live
```

Run once:

```bash
python -m app.main --once
```

CLI overrides (examples):

```bash
python -m app.main --once --symbols SPY,AAPL --dry-run
python -m app.main --once --symbols SPY --qty 2 --short-window 10 --long-window 30
python -m app.main --once --live
python -m app.main --once --strategy hft_pulse --hft-flip-seconds 1 --live
python -m app.main --strategy hft_pulse --interval-seconds 15 --live
python -m app.main --strategy hft_pulse --interval-seconds 5 --max-passes 20 --dry-run
python -m app.main --data-source alpaca --timeframe 1Min --live
python -m app.main --backtest --data-source csv --historical-dir historical_data
```

Notes:
- `--dry-run` prints intended orders and does not send them.
- `--live` disables dry run and submits orders to `ALPACA_BASE_URL`.
- Trading mode always uses Alpaca live pricing for strategy decisions.
- `--backtest --data-source csv` runs historical simulation and does not place broker orders.
- Without `--once`, the bot runs continuously until Ctrl+C.
- `--interval-seconds` controls delay between polling passes (default from `LOOP_INTERVAL_SECONDS`).
- `--max-passes` is useful for short demos/tests of loop mode.
- With `ALLOW_SHORT=true`, SELL signals can open short positions when flat.
- Account day P/L is shown each pass in green/red in a real terminal.
- Keep `ALPACA_BASE_URL` on paper endpoint for safe practice.

CSV format for backtesting:
- File path: `{HISTORICAL_DATA_DIR}/{SYMBOL}.csv`
- Required columns: `date,open,high,low,close,volume`

## Strategy

Included strategies:
- **SMA crossover**
  - BUY when short SMA crosses above long SMA
  - SELL when short SMA crosses below long SMA
  - HOLD otherwise
- **HFT pulse (demo)**
  - If short-term momentum is strong, follow momentum
  - If momentum is weak, alternate BUY/SELL on a clock interval
  - Designed to produce frequent action for demos; not production HFT

Parameters:
- `SMA_SHORT_WINDOW` (default `20`)
- `SMA_LONG_WINDOW` (default `50`)
- `HFT_MOMENTUM_WINDOW` (default `3`)
- `HFT_VOLATILITY_WINDOW` (default `12`)
- `HFT_MIN_VOLATILITY` (default `0.0005`)
- `HFT_FLIP_SECONDS` (default `3`)

Entertaining demo loop (intentional frequent trades):

```bash
for i in {1..6}; do
  python -m app.main --once --strategy hft_pulse --symbols SPY --qty 1 --hft-flip-seconds 1 --live
  sleep 1
done
```

## Logging

Logs always go to console.  
Optional file logging:
- set `LOG_FILE=logs/trader.log` in `.env`

## Club Extension Ideas

- Add position sizing based on risk (e.g., % of buying power)
- Add more strategies under `app/strategy/`
- Add a scheduler externally (cron, systemd timer, GitHub Actions, etc.)
- Add portfolio-level risk controls before order submission

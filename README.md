# algotrade

Algorithmic trading boilerplate with:

- backtest mode (CSV data)
- live mode (Alpaca)
- pluggable strategies (`sma_crossover`, `momentum`, `scalping`)
- risk gates and duplicate-order protection
- JSONL event logs and per-run Plotly reports

## Installation

### Prerequisites

- Python `3.11+`
- [`uv`](https://docs.astral.sh/uv/)

### Setup

1. Install dependencies:

```bash
uv sync --dev
```

2. Create local environment config:

```bash
cp .env.example .env
```

3. If you will run live mode, set Alpaca credentials in `.env`:

```bash
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

4. Optional sanity check:

```bash
uv run algotrade --help
```

## Quick Start

### Backtest (CSV)

```bash
uv run algotrade --mode backtest --strategy sma_crossover --once
```

Backtest defaults to CSV via `historical_data/`.

### Live (Alpaca)

```bash
uv run algotrade --mode live --strategy momentum --symbols SPY --once
```

`live` mode runs continuously by default unless `--once` is provided.

## Configuration

Runtime settings are loaded from `.env` and can be overridden via CLI flags.

### Asset Universe

Use universe variables for tradable assets:

```bash
ASSET_UNIVERSE=stocks    # stocks | crypto | all
STOCK_UNIVERSE=SPY,QQQ,AAPL
CRYPTO_UNIVERSE=BTCUSD,ETHUSD
```

Set `SYMBOLS=...` (or pass `--symbols ...`) to override universes explicitly.

For CSV backtests, symbols can include market prefixes, for example `CRYPTO:BTCUSD`, which resolves to `historical_data/CRYPTO/BTCUSD.csv`.

### Useful `.env` keys

```bash
MODE=live
STRATEGY=sma_crossover
DATA_SOURCE=auto          # auto | csv | alpaca
INTERVAL_SECONDS=5
ORDER_QTY=1
ALLOW_SHORT=true
MAX_ABS_POSITION_PER_SYMBOL=100
EVENTS_DIR=runs
STATE_DB_PATH=state/algotrade_state.db
```

## CLI Reference

```bash
uv run algotrade [options]
```

Supported options:

- `--mode {backtest,live}`
- `--strategy <id>`
- `--symbols <comma,separated>`
- `--once`
- `--continuous`
- `--interval-seconds <int>`
- `--historical-dir <path>`
- `--state-db <path>`
- `--events-dir <path>`
- `--data-source {alpaca,csv,auto}`

## Strategies

- `sma_crossover`
- `momentum`
- `scalping`

Strategy params are configured through `.env` (see `.env.example`).

## Output

Each run writes artifacts to `runs/<run_id>/`:

- `events.jsonl`: structured event stream (`run_started`, `decision`, `order_submit`, `order_update`, `cycle_summary`, `error`)
- `report.html`: interactive Plotly summary

## Development

Run checks locally:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

## Project Layout

```text
src/algotrade/
  cli.py
  config.py
  runtime.py
  brokers/
  data/
  domain/
  execution/
  logging/
  state/
  strategies/
tests/
```

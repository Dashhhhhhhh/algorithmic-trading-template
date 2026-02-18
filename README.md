# algotrade

Algorithmic trading CLI with backtest and live execution, pluggable strategies, risk gates, JSONL logs, and per-run Plotly reports.

## Installation

### Prerequisites

- Python `3.11+`
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)

### Setup

1. Install dependencies:

```bash
uv sync --dev
```

2. Create your local env file:

```bash
cp .env.example .env
```

3. For live mode, set Alpaca credentials in `.env`:

```bash
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

4. Verify CLI wiring:

```bash
uv run algotrade --help
```

## Run Model

Execution is mode-driven:

- `live`: runs continuously by default
- `backtest`: runs a finite number of cycles (defaults to `1`)

Use `--cycles N` (or `CYCLES=N`) to force a finite run in either mode.

- `N` must be `>= 1`
- exactly `N` full cycles are executed, then the process exits

## Quick Start

### Backtest (single cycle default)

```bash
uv run algotrade --mode backtest --strategy sma_crossover
```

Backtest CSV runs replay bars in walk-forward order across cycles. Once the end of a symbol's dataset is reached, subsequent cycles use the final bar and PnL will plateau.

### Backtest (fixed cycle count)

```bash
uv run algotrade --mode backtest --strategy momentum --cycles 5
```

### Live (continuous default)

```bash
uv run algotrade --mode live --strategy momentum --symbols SPY
```

### Live (finite cycle count)

```bash
uv run algotrade --mode live --strategy momentum --symbols SPY --cycles 3
```

## Configuration

Settings load from `.env` and can be overridden by CLI flags.

### Asset Universe

```bash
ASSET_UNIVERSE=stocks    # stocks | crypto | all
STOCK_UNIVERSE=SPY,QQQ,AAPL
CRYPTO_UNIVERSE=BTCUSD,ETHUSD
```

Set `SYMBOLS=...` (or `--symbols ...`) to explicitly override the universe.

For CSV backtests, symbols can include market prefixes, for example `CRYPTO:BTCUSD` which resolves to `historical_data/CRYPTO/BTCUSD.csv`.

### Cycle Timing

`INTERVAL_SECONDS` controls how often a full cycle runs (fetch data -> decide -> submit).
`POLLING_INTERVAL_SECONDS` is supported as an alias.

Example:

```bash
INTERVAL_SECONDS=5
```

In finite mode (`--cycles N`), interval applies between cycles. In continuous live mode, it applies indefinitely.

## CLI Reference

```bash
uv run algotrade [options]
```

Supported options:

- `--mode {backtest,live}`
- `--strategy <id>`
- `--symbols <comma,separated>`
- `--cycles <N>`
- `--interval-seconds <int>`
- `--historical-dir <path>`
- `--state-db <path>`
- `--events-dir <path>`
- `--data-source {alpaca,csv,auto}`

## Strategies

- `sma_crossover`
- `momentum`
- `scalping`

Strategy parameters are configured in `.env` (see `.env.example`).

## Output

Each run writes artifacts to `runs/<run_id>/`:

- `events.jsonl` with `run_started`, `decision`, `order_submit`, `order_update`, `cycle_summary`, `error`
- `report.html` Plotly summary

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

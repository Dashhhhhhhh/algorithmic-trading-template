# algotrade

Algorithmic trading CLI with backtest and live execution, pluggable strategies, risk gates, JSONL logs, and per-run Plotly reports.

## Installation

### Prerequisites (install these before installing the repository)

- Python `3.11+`
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)

### Setup

1. create a folder anywhere on your computer, name it anything.
2. open terminal and type ```cd "path/to/folder/here"``` and hit enter
3. copy ```git clone https://github.com/Dashhhhhhhh/algorithmic-trading-template.git``` into console 
4. type ```cd algorithmic-trading-template```, to enter into the cloned git directory

1. Install dependencies:

```bash
uv sync --dev
```

2. Create your local env file:

```bash
cp .env.example .env 
```
if that doesnt work just make a file named .env, and copy contents of .env.example into there

open a text editor (i prefer vscode https://code.visualstudio.com/download)


3. set Alpaca credentials in `.env`:

```bash
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

4. Verify Command Line Interface (CLI):

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

### live trading is continuous unless specified otherwise

```bash
uv run algotrade --mode live --strategy scalping
```
this will run the prewritten scalping strategy continuously until you stop (ctrl-c)


Backtest C runs replay bars in walk-forward order across cycles. Once the end of a symbol's dataset is reached, subsequent cycles use the final bar and PnL will plateau.

### Backtest (runs on preset historical data typically in a .csv/excellike format) (fixed cycle count)

```bash
uv run algotrade --mode backtest --strategy momentum --cycles 5
```


### Live (finite cycle count)

```bash
uv run algotrade --mode live --strategy momentum --symbols SPY --cycles 3
```

### Liquidate (flatten all live positions and exit)

```bash
uv run algotrade --liquidate
```

### Portfolio (list current balances and positions)

```bash
uv run algotrade --portfolio
```

In live mode, portfolio output includes per-position quantity and, when available from Alpaca,
cash value/cost details (market value, cost basis, unrealized P/L).

## Configuration

Settings load from `.env` and can be overridden by CLI flags.

### Asset Universe

basically what assets are being traded

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

### Position Sizing

By default, live/backtest order quantities are computed using notional sizing so the system can trade
fractional stock/crypto quantities instead of requiring whole units.

```bash
ORDER_SIZING_METHOD=notional   # notional | units
ORDER_NOTIONAL_USD=100         # dollar exposure per +1/-1 target unit
MIN_TRADE_QTY=0.0001           # skip tiny deltas below this quantity
QTY_PRECISION=6                # quantity rounding precision
```

Use `ORDER_SIZING_METHOD=units` to keep legacy whole-unit target behavior.

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
- `--liquidate`
- `--portfolio`

## Output

Each run writes artifacts to `runs/<run_id>/`:

- `events.jsonl` with `run_started`, `decision`, `order_submit`, `order_update`, `cycle_summary`, `error`
- `report.html` Plotly summary



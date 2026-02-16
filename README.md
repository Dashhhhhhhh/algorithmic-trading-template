# algotrade

Minimal algorithmic trading boilerplate with a `src` layout, stable target-position strategy contracts, backtest and Alpaca paper/live modes, JSONL event logs, and per-run Plotly reports.

## Installation with uv

```bash
uv sync --dev
```

## Project layout

```text
src/algotrade/
  cli.py
  config.py
  runtime.py
  domain/
  data/
  brokers/
  strategies/
  execution/
  logging/
  state/
tests/
```

## Run backtest mode

Backtest defaults to CSV data via `historical_data`.

```bash
uv run algotrade --mode backtest --strategy sma_crossover --symbols SPY --once
```

## Run paper mode

Paper and live modes share the Alpaca broker implementation and use `ALPACA_BASE_URL` to choose endpoint behavior.

```bash
uv run algotrade --mode paper --strategy momentum --symbols SPY --once
```

## Run live mode

```bash
uv run algotrade --mode live --strategy momentum --symbols SPY --continuous
```

## Add a new strategy

1. Copy `/Users/dashdunmire/Documents/algotrade/boilerplate/src/algotrade/strategies/strategy_template.py` to a new module in `/Users/dashdunmire/Documents/algotrade/boilerplate/src/algotrade/strategies/`.
2. Set a stable `strategy_id` and implement `decide_targets(bars_by_symbol, portfolio_snapshot) -> dict[str, int]`.
3. Register the factory in `/Users/dashdunmire/Documents/algotrade/boilerplate/src/algotrade/strategies/registry.py`.

## Logging and dashboards

Each run writes output under `/Users/dashdunmire/Documents/algotrade/boilerplate/runs/<run_id>/`:

- `events.jsonl` with schema `ts, run_id, mode, strategy_id, event_type, payload`
- `report.html` interactive Plotly event timeline and counts

Human console logs emit only these line types:

- `run_started`
- `decision`
- `order_submit`
- `order_update`
- `error`

## CI

GitHub Actions workflow is at `/Users/dashdunmire/Documents/algotrade/boilerplate/.github/workflows/ci.yml` and runs:

- `uv sync --dev`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q`

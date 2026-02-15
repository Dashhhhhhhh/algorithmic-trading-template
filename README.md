# Bare-Bones Algorithmic Trading Boilerplate (Python)

Minimal, beginner-friendly starter for a student club.  
This project runs one end-to-end cycle:
1. Fetch historical daily data from Alpha Vantage
2. Generate a toy signal (SMA crossover)
3. Send market orders to Alpaca (or simulate in dry run)
4. Log each step clearly

## Project Structure

```text
.
├── .env.example
├── README.md
├── requirements.txt
├── app
│   ├── __init__.py
│   ├── config.py
│   ├── logging_utils.py
│   ├── main.py
│   ├── broker
│   │   ├── __init__.py
│   │   ├── alpaca.py
│   │   └── models.py
│   ├── data
│   │   ├── __init__.py
│   │   ├── alpha_vantage.py
│   │   └── models.py
│   ├── execution
│   │   ├── __init__.py
│   │   └── trader.py
│   ├── strategy
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── sma_crossover.py
│   └── utils
│       ├── __init__.py
│       ├── errors.py
│       └── time.py
└── tests
    └── test_sma_crossover.py
```

## Requirements

- Python 3.11+
- Alpha Vantage API key (free tier available)
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

Required variables:
- `ALPHA_VANTAGE_API_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`

Key defaults:
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
- `SYMBOLS=SPY`
- `STRATEGY=sma_crossover`
- `DRY_RUN=true`
- `ORDER_QTY=1`

## Run

Run once:

```bash
python -m app.main --once
```

CLI overrides (examples):

```bash
python -m app.main --once --symbols SPY,AAPL --dry-run
python -m app.main --once --symbols SPY --qty 2 --short-window 10 --long-window 30
python -m app.main --once --live
```

Notes:
- `--dry-run` prints intended orders and does not send them.
- `--live` disables dry run and submits orders to `ALPACA_BASE_URL`.
- Keep `ALPACA_BASE_URL` on paper endpoint for safe practice.

## Strategy

Included strategy: **SMA crossover**
- BUY when short SMA crosses above long SMA
- SELL when short SMA crosses below long SMA
- HOLD otherwise

Parameters:
- `SMA_SHORT_WINDOW` (default `20`)
- `SMA_LONG_WINDOW` (default `50`)

## Logging

Logs always go to console.  
Optional file logging:
- set `LOG_FILE=logs/trader.log` in `.env`

## Club Extension Ideas

- Add position sizing based on risk (e.g., % of buying power)
- Add more strategies under `app/strategy/`
- Add a scheduler externally (cron, systemd timer, GitHub Actions, etc.)
- Add portfolio-level risk controls before order submission


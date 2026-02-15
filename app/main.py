"""CLI entry point for the algorithmic trading boilerplate."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace

from app.backtest import run_backtest_for_symbol
from app.broker.alpaca import AlpacaClient
from app.config import Settings
from app.data.alpaca_data import AlpacaDataClient
from app.data.base import MarketDataClient
from app.data.csv_data import CsvDataClient
from app.execution.trader import Trader
from app.logging_utils import setup_logger
from app.strategy.base import Strategy
from app.strategy.loader import create_strategy
from app.utils.errors import ConfigError, TradingAppError


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments that can override environment configuration."""
    parser = argparse.ArgumentParser(description="Bare-bones algorithmic trading runner")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g. SPY,AAPL)")
    parser.add_argument("--strategy", type=str, help="Strategy module name from app/strategy/")
    parser.add_argument(
        "--data-source",
        type=str,
        help="Market data source: alpaca (default) or csv (backtest only)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        help="Bar timeframe (examples: 1D, 1Min, 5Min)",
    )
    parser.add_argument(
        "--historical-dir",
        type=str,
        help="Directory for local CSV historical data (DATA_SOURCE=csv)",
    )
    parser.add_argument("--qty", type=int, help="Order quantity per trade")
    parser.add_argument("--once", action="store_true", help="Run one trading pass and exit")
    parser.add_argument("--backtest", action="store_true", help="Run historical backtest and exit")
    parser.add_argument(
        "--backtest-cash",
        type=float,
        help="Starting cash for backtest mode",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        help="Seconds between polling passes in continuous mode",
    )
    parser.add_argument(
        "--max-passes",
        "--max-cycles",
        dest="max_cycles",
        type=int,
        help="Stop after N passes (for testing); default runs indefinitely",
    )
    dry_group = parser.add_mutually_exclusive_group()
    dry_group.add_argument("--dry-run", action="store_true", help="Do not place real orders")
    dry_group.add_argument(
        "--live",
        action="store_true",
        help="Submit real orders to ALPACA_BASE_URL (make sure this is intended).",
    )
    return parser.parse_args()


def build_strategy(name: str, settings: Settings) -> Strategy:
    """Factory for available strategies."""
    return create_strategy(name=name, settings=settings)


def apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """Merge CLI flags into environment-derived settings."""
    strategy = args.strategy or settings.strategy
    symbols = (
        [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
        if args.symbols
        else settings.symbols_for_strategy(strategy)
    )
    data_source = (args.data_source or settings.data_source).strip().lower()
    historical_data_dir = args.historical_dir or settings.historical_data_dir
    timeframe = args.timeframe or settings.timeframe
    order_qty = args.qty if args.qty is not None else settings.order_qty
    loop_interval_seconds = (
        args.interval_seconds
        if args.interval_seconds is not None
        else settings.loop_interval_seconds
    )
    dry_run = settings.dry_run
    if args.dry_run:
        dry_run = True
    if args.live:
        dry_run = False

    overridden = replace(
        settings,
        symbols=symbols,
        strategy=strategy,
        data_source=data_source,
        historical_data_dir=historical_data_dir,
        timeframe=timeframe,
        dry_run=dry_run,
        order_qty=order_qty,
        loop_interval_seconds=loop_interval_seconds,
    )
    return overridden.validate()


def build_data_client(settings: Settings) -> MarketDataClient:
    """Factory for market data providers."""
    if settings.data_source == "alpaca":
        return AlpacaDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            data_base_url=settings.alpaca_data_url,
            timeframe=settings.timeframe,
        )
    if settings.data_source == "csv":
        return CsvDataClient(data_dir=settings.historical_data_dir)
    raise ConfigError(
        f"Unsupported data source '{settings.data_source}'. "
        "Use alpaca or csv."
    )


def validate_runtime_requirements(settings: Settings, backtest_mode: bool) -> None:
    """Validate required credentials for selected runtime mode."""
    missing: list[str] = []

    # Trading decisions always use Alpaca live market data.
    if not backtest_mode or settings.data_source == "alpaca":
        if not settings.alpaca_api_key:
            missing.append("ALPACA_API_KEY")
        if not settings.alpaca_secret_key:
            missing.append("ALPACA_SECRET_KEY")

    if backtest_mode and settings.data_source != "csv":
        raise ConfigError(
            "Backtest mode requires --data-source csv (explicit historical CSV usage)."
        )
    if not backtest_mode and settings.data_source != "alpaca":
        raise ConfigError(
            "Trading mode uses Alpaca live data by default. "
            "Use --backtest --data-source csv for historical CSV runs."
        )

    if missing:
        unique_missing = sorted(set(missing))
        vars_text = ", ".join(unique_missing)
        raise ConfigError(
            f"Missing required environment variable(s): {vars_text}. "
            "Update your .env and try again."
        )


def run() -> int:
    """Program entry function. Returns process exit code."""
    args = parse_args()
    if args.max_cycles is not None and args.max_cycles <= 0:
        print("Configuration error: --max-passes must be a positive integer.")
        return 2
    if args.backtest_cash is not None and args.backtest_cash <= 0:
        print("Configuration error: --backtest-cash must be a positive number.")
        return 2

    try:
        settings = apply_cli_overrides(Settings.from_env(), args)
        validate_runtime_requirements(settings=settings, backtest_mode=args.backtest)
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 2

    logger = setup_logger(settings.log_level, settings.log_file)
    logger.info(
        "Starting trading bot | symbols=%s strategy=%s data_source=%s",
        settings.symbols,
        settings.strategy,
        settings.data_source,
    )
    mode_name = "BACKTEST" if args.backtest else ("DRY_RUN" if settings.dry_run else "LIVE")
    logger.info("Trading mode: %s", mode_name)
    logger.info("Shorting: %s", "ENABLED" if settings.allow_short else "DISABLED")
    if settings.timeframe != "1D":
        logger.warning(
            "TIMEFRAME=%s is configured, but this starter currently fetches daily bars only.",
            settings.timeframe,
        )

    if not args.backtest:
        if not settings.dry_run and "paper-api" in settings.alpaca_base_url:
            logger.warning("Live mode enabled, but base URL points to paper endpoint.")
        if settings.dry_run and "paper-api" not in settings.alpaca_base_url:
            logger.warning(
                "DRY_RUN is enabled with a non-paper base URL. No orders will be sent anyway."
            )
        recommended_interval = max(12 * len(settings.symbols), 12)
        if settings.loop_interval_seconds < recommended_interval:
            logger.warning(
                "interval=%ss may exceed data rate limits for %s symbol(s). "
                "Recommended interval >= %ss.",
                settings.loop_interval_seconds,
                len(settings.symbols),
                recommended_interval,
            )

    try:
        data_client = build_data_client(settings=settings)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    try:
        strategy = build_strategy(settings.strategy, settings)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    if args.backtest:
        starting_cash = (
            args.backtest_cash
            if args.backtest_cash is not None
            else settings.backtest_starting_cash
        )
        logger.info(
            "Running backtest | symbols=%s starting_cash=%.2f",
            settings.symbols,
            starting_cash,
        )
        for symbol in settings.symbols:
            try:
                bars = data_client.fetch_daily(symbol=symbol)
                result = run_backtest_for_symbol(
                    symbol=symbol,
                    bars=bars,
                    strategy=strategy,
                    qty=settings.order_qty,
                    allow_short=settings.allow_short,
                    starting_cash=starting_cash,
                )
                logger.info(
                    "Backtest %s | start=%.2f end=%.2f pnl=%+.2f (%+.2f%%) trades=%s rows=%s",
                    result.symbol,
                    result.start_equity,
                    result.end_equity,
                    result.pnl,
                    result.pnl_pct,
                    result.trades,
                    len(bars),
                )
            except TradingAppError as exc:
                logger.error("Backtest failed for %s: %s", symbol, exc)
            except Exception as exc:  # pragma: no cover - top-level guard
                logger.exception("Backtest unexpected error for %s: %s", symbol, exc)
        return 0

    broker_client = AlpacaClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        base_url=settings.alpaca_base_url,
    )

    trader = Trader(
        data_client=data_client,
        broker_client=broker_client,
        strategy=strategy,
        dry_run=settings.dry_run,
        default_qty=settings.order_qty,
        allow_short=settings.allow_short,
    )

    if args.once:
        try:
            trader.run_once(symbols=settings.symbols)
        except TradingAppError as exc:
            logger.error("Trading run failed: %s", exc)
            return 1
        except Exception as exc:  # pragma: no cover - top-level guard
            logger.exception("Unexpected fatal error: %s", exc)
            return 1
        return 0

    logger.info(
        "Starting continuous trading loop | interval=%ss | press Ctrl+C to stop",
        settings.loop_interval_seconds,
    )
    pass_count = 0
    try:
        while True:
            try:
                trader.run_once(symbols=settings.symbols)
            except TradingAppError as exc:
                logger.error("Continuous loop pass failed: %s", exc)
            except Exception as exc:  # pragma: no cover - top-level guard
                logger.exception("Continuous loop unexpected error: %s", exc)

            pass_count += 1
            if args.max_cycles is not None and pass_count >= args.max_cycles:
                logger.info("Reached max passes (%s). Exiting.", args.max_cycles)
                break

            time.sleep(settings.loop_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping bot.")

    logger.info("Trading bot stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(run())

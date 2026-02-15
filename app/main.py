"""CLI entry point for the algorithmic trading boilerplate."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from app.config import Settings
from app.data.alpha_vantage import AlphaVantageClient
from app.execution.trader import Trader
from app.logging_utils import setup_logger
from app.broker.alpaca import AlpacaClient
from app.strategy.base import Strategy
from app.strategy.sma_crossover import SmaCrossoverParams, SmaCrossoverStrategy
from app.utils.errors import ConfigError, TradingAppError


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments that can override environment configuration."""
    parser = argparse.ArgumentParser(description="Bare-bones algorithmic trading runner")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g. SPY,AAPL)")
    parser.add_argument("--strategy", type=str, help="Strategy name (default: sma_crossover)")
    parser.add_argument("--qty", type=int, help="Order quantity per trade")
    parser.add_argument("--once", action="store_true", help="Run one trading cycle and exit")
    parser.add_argument("--short-window", type=int, help="SMA short window override")
    parser.add_argument("--long-window", type=int, help="SMA long window override")

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
    normalized = name.strip().lower()
    if normalized == "sma_crossover":
        params = SmaCrossoverParams(
            short_window=settings.sma_short_window,
            long_window=settings.sma_long_window,
        )
        return SmaCrossoverStrategy(params=params)
    raise ConfigError(
        f"Unknown strategy '{name}'. Supported strategies: sma_crossover"
    )


def apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """Merge CLI flags into environment-derived settings."""
    symbols = settings.symbols
    if args.symbols:
        symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]

    strategy = args.strategy or settings.strategy
    order_qty = args.qty if args.qty is not None else settings.order_qty
    short_window = args.short_window or settings.sma_short_window
    long_window = args.long_window or settings.sma_long_window

    dry_run = settings.dry_run
    if args.dry_run:
        dry_run = True
    if args.live:
        dry_run = False

    overridden = replace(
        settings,
        symbols=symbols,
        strategy=strategy,
        dry_run=dry_run,
        order_qty=order_qty,
        sma_short_window=short_window,
        sma_long_window=long_window,
    )
    return overridden.validate()


def run() -> int:
    """Program entry function. Returns process exit code."""
    args = parse_args()
    try:
        settings = apply_cli_overrides(Settings.from_env(), args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 2

    logger = setup_logger(settings.log_level, settings.log_file)
    logger.info("Starting trading run | symbols=%s strategy=%s", settings.symbols, settings.strategy)
    logger.info("Trading mode: %s", "DRY_RUN" if settings.dry_run else "LIVE")
    if settings.timeframe != "1D":
        logger.warning(
            "TIMEFRAME=%s is configured, but this starter currently fetches daily bars only.",
            settings.timeframe,
        )

    if not settings.dry_run and "paper-api" in settings.alpaca_base_url:
        logger.warning("Live mode enabled, but base URL points to paper endpoint.")
    if settings.dry_run and "paper-api" not in settings.alpaca_base_url:
        logger.warning(
            "DRY_RUN is enabled with a non-paper base URL. No orders will be sent anyway."
        )

    data_client = AlphaVantageClient(api_key=settings.alpha_vantage_api_key)
    broker_client = AlpacaClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        base_url=settings.alpaca_base_url,
    )

    try:
        strategy = build_strategy(settings.strategy, settings)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    trader = Trader(
        data_client=data_client,
        broker_client=broker_client,
        strategy=strategy,
        dry_run=settings.dry_run,
        default_qty=settings.order_qty,
    )

    try:
        trader.run_once(symbols=settings.symbols)
    except TradingAppError as exc:
        logger.error("Trading run failed: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover - top-level guard
        logger.exception("Unexpected fatal error: %s", exc)
        return 1

    if not args.once:
        logger.info(
            "Run completed once. For scheduling, use cron or a job runner later "
            "(intentionally not built into this starter)."
        )

    logger.info("Trading run complete.")
    return 0


if __name__ == "__main__":
    sys.exit(run())

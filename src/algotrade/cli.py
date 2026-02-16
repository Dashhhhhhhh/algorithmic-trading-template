"""Command-line interface for algotrade runtime."""

from __future__ import annotations

import argparse
import sys

from algotrade.config import Settings, parse_symbols
from algotrade.runtime import run
from algotrade.strategies.registry import available_strategy_ids


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Minimal algorithmic trading boilerplate")
    parser.add_argument("--mode", choices=["backtest", "paper", "live"], help="Runtime mode")
    parser.add_argument("--strategy", type=str, help="Strategy id")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--once", action="store_true", help="Run one cycle")
    parser.add_argument("--continuous", action="store_true", help="Run continuously")
    parser.add_argument("--interval-seconds", type=int, help="Seconds between continuous cycles")
    parser.add_argument("--historical-dir", type=str, help="CSV historical data directory")
    parser.add_argument("--state-db", type=str, help="SQLite state database path")
    parser.add_argument("--events-dir", type=str, help="Run outputs directory")
    parser.add_argument("--data-source", choices=["alpaca", "csv", "auto"], help="Data source")
    return parser


def apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """Apply CLI values onto environment-derived settings."""
    if args.once and args.continuous:
        raise ValueError("Use either --once or --continuous, not both")

    overrides: dict[str, object] = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.strategy:
        overrides["strategy"] = args.strategy
    if args.symbols:
        overrides["symbols"] = parse_symbols(args.symbols, settings.symbols)
    if args.once:
        overrides["once"] = True
        overrides["continuous"] = False
    if args.continuous:
        overrides["continuous"] = True
        overrides["once"] = False
    if args.interval_seconds is not None:
        overrides["interval_seconds"] = args.interval_seconds
    if args.historical_dir:
        overrides["historical_data_dir"] = args.historical_dir
    if args.state_db:
        overrides["state_db_path"] = args.state_db
    if args.events_dir:
        overrides["events_dir"] = args.events_dir
    if args.data_source:
        overrides["data_source"] = args.data_source

    merged = settings.with_overrides(**overrides)
    if merged.strategy not in available_strategy_ids():
        supported = ", ".join(available_strategy_ids())
        raise ValueError(f"Unknown strategy '{merged.strategy}'. Supported: {supported}")
    return merged


def main() -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        settings = apply_cli_overrides(Settings.from_env(), args)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2
    return run(settings)


if __name__ == "__main__":
    sys.exit(main())

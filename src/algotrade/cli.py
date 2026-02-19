"""Command-line interface for algotrade runtime."""

from __future__ import annotations

import argparse
import sys

from algotrade.config import Settings, parse_symbols
from algotrade.runtime import liquidate, run, show_portfolio
from algotrade.strategy_core.registry import available_strategy_ids, default_strategy_id


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Minimal algorithmic trading boilerplate")
    parser.add_argument("--mode", choices=["backtest", "live"], help="Runtime mode")
    parser.add_argument("--strategy", type=str, help="Strategy id")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--max-passes", type=int, help="Run a fixed number of live passes")
    parser.add_argument(
        "--backtest-max-steps",
        type=int,
        help="Cap walk-forward steps in backtest mode",
    )
    parser.add_argument(
        "--interval-seconds", type=int, help="Seconds between full live execution passes"
    )
    parser.add_argument("--historical-dir", type=str, help="CSV historical data directory")
    parser.add_argument("--state-db", type=str, help="SQLite state database path")
    parser.add_argument("--events-dir", type=str, help="Run outputs directory")
    parser.add_argument("--data-source", choices=["alpaca", "csv", "auto"], help="Data source")
    parser.add_argument(
        "--liquidate",
        action="store_true",
        help="Submit offsetting market orders to flatten all live positions, then exit",
    )
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="List current live portfolio balances and positions, then exit",
    )
    return parser


def apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    """Apply CLI values onto environment-derived settings."""
    requested_mode = args.mode or settings.mode
    if args.max_passes is not None and requested_mode != "live":
        raise ValueError("--max-passes requires --mode live")
    if args.backtest_max_steps is not None and requested_mode != "backtest":
        raise ValueError("--backtest-max-steps requires --mode backtest")

    overrides: dict[str, object] = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.strategy:
        overrides["strategy"] = args.strategy
    if args.symbols:
        overrides["symbols"] = parse_symbols(args.symbols, settings.symbols)
    if args.max_passes is not None:
        overrides["max_passes"] = args.max_passes
    if args.backtest_max_steps is not None:
        overrides["backtest_max_steps"] = args.backtest_max_steps
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
    if not merged.strategy.strip():
        merged = merged.with_overrides(strategy=default_strategy_id())
    if args.liquidate and args.portfolio:
        raise ValueError("Use only one action flag: --liquidate or --portfolio")
    if args.liquidate and merged.mode != "live":
        raise ValueError("--liquidate requires --mode live")
    if args.portfolio and merged.mode != "live":
        raise ValueError("--portfolio requires --mode live")
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
    if args.liquidate:
        return liquidate(settings)
    if args.portfolio:
        return show_portfolio(settings)
    return run(settings)


if __name__ == "__main__":
    sys.exit(main())

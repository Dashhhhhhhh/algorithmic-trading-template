"""Tests for CLI override behavior."""

from __future__ import annotations

from argparse import Namespace

from app.config import Settings
from app.main import apply_cli_overrides


def test_interval_seconds_cli_override() -> None:
    settings = Settings(
        alpaca_api_key="y",
        alpaca_secret_key="z",
        symbols=["SPY"],
    )
    args = Namespace(
        symbols=None,
        strategy=None,
        data_source=None,
        timeframe=None,
        historical_dir=None,
        qty=None,
        once=True,
        backtest=False,
        backtest_cash=None,
        interval_seconds=9,
        max_cycles=None,
        short_window=None,
        long_window=None,
        hft_momentum_window=None,
        hft_volatility_window=None,
        hft_min_volatility=None,
        hft_flip_seconds=None,
        dry_run=False,
        live=False,
    )

    merged = apply_cli_overrides(settings, args)
    assert merged.loop_interval_seconds == 9

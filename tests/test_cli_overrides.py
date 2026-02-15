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
        dry_run=False,
        live=False,
    )

    merged = apply_cli_overrides(settings, args)
    assert merged.loop_interval_seconds == 9


def test_strategy_universe_env_is_used_when_symbols_not_overridden(monkeypatch) -> None:
    monkeypatch.setenv("HFT_PULSE_SYMBOLS", "TSLA,QQQ")
    settings = Settings(
        alpaca_api_key="y",
        alpaca_secret_key="z",
        symbols=["SPY"],
        strategy="sma_crossover",
    )
    args = Namespace(
        symbols=None,
        strategy="hft_pulse",
        data_source=None,
        timeframe=None,
        historical_dir=None,
        qty=None,
        once=True,
        backtest=False,
        backtest_cash=None,
        interval_seconds=None,
        max_cycles=None,
        dry_run=False,
        live=False,
    )

    merged = apply_cli_overrides(settings, args)
    assert merged.symbols == ["TSLA", "QQQ"]


def test_blank_strategy_universe_falls_back_to_global_symbols(monkeypatch) -> None:
    monkeypatch.setenv("HFT_PULSE_SYMBOLS", "   ")
    settings = Settings(
        alpaca_api_key="y",
        alpaca_secret_key="z",
        symbols=["SPY", "AAPL"],
        strategy="sma_crossover",
    )
    args = Namespace(
        symbols=None,
        strategy="hft_pulse",
        data_source=None,
        timeframe=None,
        historical_dir=None,
        qty=None,
        once=True,
        backtest=False,
        backtest_cash=None,
        interval_seconds=None,
        max_cycles=None,
        dry_run=False,
        live=False,
    )

    merged = apply_cli_overrides(settings, args)
    assert merged.symbols == ["SPY", "AAPL"]

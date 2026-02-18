from __future__ import annotations

import pytest

from algotrade.cli import apply_cli_overrides, build_parser
from algotrade.config import Settings


def test_cli_overrides_produce_expected_settings() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--mode",
            "backtest",
            "--strategy",
            "momentum",
            "--symbols",
            "SPY,AAPL",
            "--once",
            "--interval-seconds",
            "9",
            "--historical-dir",
            "historical_data",
            "--state-db",
            "state/test.db",
            "--events-dir",
            "runs/test",
            "--data-source",
            "csv",
        ]
    )
    settings = apply_cli_overrides(Settings(), args)

    assert settings.mode == "backtest"
    assert settings.strategy == "momentum"
    assert settings.symbols == ["SPY", "AAPL"]
    assert settings.once is True
    assert settings.continuous is False
    assert settings.interval_seconds == 9
    assert settings.historical_data_dir == "historical_data"
    assert settings.state_db_path == "state/test.db"
    assert settings.events_dir == "runs/test"
    assert settings.effective_data_source() == "csv"


def test_cli_rejects_once_and_continuous_together() -> None:
    parser = build_parser()
    args = parser.parse_args(["--once", "--continuous"])

    with pytest.raises(ValueError):
        apply_cli_overrides(Settings(), args)


def test_backtest_defaults_to_single_cycle_without_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.once is False
    assert settings.continuous is False
    assert settings.should_run_continuously() is False


def test_live_defaults_to_continuous_without_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "live"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.once is False
    assert settings.continuous is False
    assert settings.should_run_continuously() is True


def test_cli_accepts_scalping_strategy() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--strategy", "scalping"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.strategy == "scalping"

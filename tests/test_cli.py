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
            "cross_sectional_momentum",
            "--symbols",
            "SPY,AAPL",
            "--backtest-max-steps",
            "3",
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
    assert settings.strategy == "cross_sectional_momentum"
    assert settings.symbols == ["SPY", "AAPL"]
    assert settings.backtest_max_steps == 3
    assert settings.backtest_step_cap() == 3
    assert settings.interval_seconds == 9
    assert settings.historical_data_dir == "historical_data"
    assert settings.state_db_path == "state/test.db"
    assert settings.events_dir == "runs/test"
    assert settings.effective_data_source() == "csv"


def test_cli_rejects_non_positive_max_passes() -> None:
    parser = build_parser()
    args = parser.parse_args(["--max-passes", "0"])

    with pytest.raises(ValueError):
        apply_cli_overrides(Settings(), args)


def test_cli_rejects_non_positive_backtest_step_cap() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--backtest-max-steps", "0"])

    with pytest.raises(ValueError):
        apply_cli_overrides(Settings(), args)


def test_backtest_defaults_to_full_history_without_step_cap() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.backtest_max_steps is None
    assert settings.backtest_step_cap() is None


def test_live_defaults_to_continuous_without_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "live"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.max_passes is None
    assert settings.live_pass_limit() is None


def test_live_can_be_limited_with_max_passes() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "live", "--max-passes", "2"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.mode == "live"
    assert settings.live_pass_limit() == 2


def test_cli_rejects_max_passes_in_backtest_mode() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--max-passes", "2"])

    with pytest.raises(ValueError, match="--max-passes requires --mode live"):
        apply_cli_overrides(Settings(), args)


def test_cli_rejects_backtest_max_steps_in_live_mode() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "live", "--backtest-max-steps", "2"])

    with pytest.raises(ValueError, match="--backtest-max-steps requires --mode backtest"):
        apply_cli_overrides(Settings(), args)


def test_cli_does_not_accept_legacy_once_or_continuous_flags() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--once"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--continuous"])


def test_cli_accepts_scalping_strategy() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--strategy", "scalping"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.strategy == "scalping"


def test_cli_accepts_cross_sectional_momentum_strategy() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--strategy", "cross_sectional_momentum"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.strategy == "cross_sectional_momentum"


def test_cli_accepts_arbitrage_strategy() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--strategy", "arbitrage"])
    settings = apply_cli_overrides(Settings(), args)

    assert settings.strategy == "arbitrage"


def test_cli_accepts_liquidate_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--liquidate"])

    assert args.liquidate is True


def test_cli_rejects_liquidate_in_backtest_mode() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--liquidate"])

    with pytest.raises(ValueError, match="--liquidate requires --mode live"):
        apply_cli_overrides(Settings(), args)


def test_cli_accepts_portfolio_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--portfolio"])

    assert args.portfolio is True


def test_cli_rejects_portfolio_in_backtest_mode() -> None:
    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--portfolio"])

    with pytest.raises(ValueError, match="--portfolio requires --mode live"):
        apply_cli_overrides(Settings(), args)


def test_cli_rejects_multiple_action_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--liquidate", "--portfolio"])

    with pytest.raises(ValueError, match="Use only one action flag"):
        apply_cli_overrides(Settings(), args)

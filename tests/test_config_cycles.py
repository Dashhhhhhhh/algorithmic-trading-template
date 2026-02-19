from __future__ import annotations

import pytest

from algotrade.config import Settings

ENV_KEYS = [
    "MODE",
    "MAX_PASSES",
    "BACKTEST_MAX_STEPS",
    "CYCLES",
    "INTERVAL_SECONDS",
    "POLLING_INTERVAL_SECONDS",
]


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_from_env_uses_polling_interval_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("POLLING_INTERVAL_SECONDS", "7")

    settings = Settings.from_env()

    assert settings.interval_seconds == 7


def test_pass_limits_default_by_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("MODE", "backtest")

    backtest_settings = Settings.from_env()
    assert backtest_settings.backtest_step_cap() is None
    assert backtest_settings.live_pass_limit() is None

    monkeypatch.setenv("MODE", "live")
    live_settings = Settings.from_env()
    assert live_settings.live_pass_limit() is None
    assert live_settings.backtest_step_cap() is None


def test_live_pass_limit_uses_explicit_max_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("MAX_PASSES", "4")

    settings = Settings.from_env()

    assert settings.max_passes == 4
    assert settings.live_pass_limit() == 4


def test_legacy_cycles_alias_is_live_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("CYCLES", "3")
    monkeypatch.setenv("MODE", "live")

    live_settings = Settings.from_env()
    assert live_settings.max_passes == 3

    monkeypatch.setenv("MODE", "backtest")
    backtest_settings = Settings.from_env()
    assert backtest_settings.max_passes is None


def test_from_env_rejects_non_positive_max_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("MAX_PASSES", "0")
    monkeypatch.setenv("MODE", "live")

    with pytest.raises(ValueError, match="max_passes must be positive"):
        Settings.from_env()


def test_from_env_rejects_non_positive_backtest_max_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("BACKTEST_MAX_STEPS", "0")
    monkeypatch.setenv("MODE", "backtest")

    with pytest.raises(ValueError, match="backtest_max_steps must be positive"):
        Settings.from_env()

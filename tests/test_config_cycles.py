from __future__ import annotations

import pytest

from algotrade.config import Settings

ENV_KEYS = [
    "MODE",
    "CYCLES",
    "INTERVAL_SECONDS",
    "POLLING_INTERVAL_SECONDS",
]


def _clear_cycle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_from_env_uses_polling_interval_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_cycle_env(monkeypatch)
    monkeypatch.setenv("POLLING_INTERVAL_SECONDS", "7")

    settings = Settings.from_env()

    assert settings.interval_seconds == 7


def test_cycle_limit_defaults_by_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_cycle_env(monkeypatch)
    monkeypatch.setenv("MODE", "backtest")

    backtest_settings = Settings.from_env()
    assert backtest_settings.cycle_limit() == 1

    monkeypatch.setenv("MODE", "live")
    live_settings = Settings.from_env()
    assert live_settings.cycle_limit() is None


def test_cycle_limit_uses_explicit_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_cycle_env(monkeypatch)
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("CYCLES", "4")

    settings = Settings.from_env()

    assert settings.cycles == 4
    assert settings.cycle_limit() == 4


def test_from_env_rejects_non_positive_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_cycle_env(monkeypatch)
    monkeypatch.setenv("CYCLES", "0")

    with pytest.raises(ValueError, match="cycles must be positive"):
        Settings.from_env()

from __future__ import annotations

import pytest

from algotrade.cli import apply_cli_overrides, build_parser
from algotrade.config import Settings

ENV_KEYS = [
    "MODE",
    "STRATEGY",
    "SYMBOLS",
    "INTERVAL_SECONDS",
]


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_precedence_env_then_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("STRATEGY", "scalping")
    monkeypatch.setenv("SYMBOLS", "SPY,QQQ")
    monkeypatch.setenv("INTERVAL_SECONDS", "9")

    settings = Settings.from_env()
    assert settings.mode == "live"
    assert settings.strategy == "scalping"
    assert settings.symbols == ["SPY", "QQQ"]
    assert settings.interval_seconds == 9

    parser = build_parser()
    args = parser.parse_args(
        [
            "--mode",
            "backtest",
            "--strategy",
            "cross_sectional_momentum",
            "--cycles",
            "1",
        ]
    )
    merged = apply_cli_overrides(settings, args)

    assert merged.mode == "backtest"
    assert merged.strategy == "cross_sectional_momentum"
    assert merged.cycles == 1


def test_mode_paper_is_normalized_to_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("MODE", "paper")

    settings = Settings.from_env()

    assert settings.mode == "live"

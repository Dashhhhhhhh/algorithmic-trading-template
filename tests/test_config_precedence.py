from __future__ import annotations

from pathlib import Path

import pytest

from algotrade.cli import apply_cli_overrides, build_parser
from algotrade.config import Settings

ENV_KEYS = [
    "MODE",
    "STRATEGY",
    "SYMBOLS",
    "INTERVAL_SECONDS",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_PAPER",
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
]


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_precedence_config_env_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)

    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        """
[runtime]
mode = "backtest"
strategy = "sma_crossover"
symbols = ["MSFT"]
interval_seconds = 11

[alpaca]
api_key = "config_key"
secret_key = "config_secret"
paper = true
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("STRATEGY", "momentum")
    monkeypatch.setenv("SYMBOLS", "SPY,QQQ")
    monkeypatch.setenv("INTERVAL_SECONDS", "9")
    monkeypatch.setenv("ALPACA_API_KEY", "env_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "env_secret")

    settings = Settings.load(config_path)
    assert settings.mode == "paper"
    assert settings.strategy == "momentum"
    assert settings.symbols == ["SPY", "QQQ"]
    assert settings.interval_seconds == 9
    assert settings.alpaca_api_key == "env_key"

    parser = build_parser()
    args = parser.parse_args(["--mode", "backtest", "--strategy", "sma_crossover", "--cycles", "1"])
    merged = apply_cli_overrides(settings, args)

    assert merged.mode == "backtest"
    assert merged.strategy == "sma_crossover"
    assert merged.cycles == 1


def test_settings_requires_alpaca_credentials_for_paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)
    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("ALPACA_API_KEY", "")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "")

    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        Settings.load(config_path=None)


def test_settings_supports_legacy_alpaca_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_env(monkeypatch)

    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("APCA_API_KEY_ID", "legacy_key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "legacy_secret")

    settings = Settings.load(config_path=None)

    assert settings.alpaca_api_key == "legacy_key"
    assert settings.alpaca_secret_key == "legacy_secret"

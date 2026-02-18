from __future__ import annotations

import pytest

from algotrade.config import Settings

UNIVERSE_ENV_KEYS = [
    "MODE",
    "SYMBOLS",
    "ASSET_UNIVERSE",
    "STOCK_UNIVERSE",
    "CRYPTO_UNIVERSE",
]


def _clear_universe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in UNIVERSE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_from_env_uses_stock_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_universe_env(monkeypatch)
    monkeypatch.setenv("MODE", "backtest")
    monkeypatch.setenv("ASSET_UNIVERSE", "stocks")
    monkeypatch.setenv("STOCK_UNIVERSE", "spy,msft")
    monkeypatch.setenv("CRYPTO_UNIVERSE", "BTCUSD,ETHUSD")

    settings = Settings.from_env()

    assert settings.symbols == ["SPY", "MSFT"]


def test_settings_from_env_uses_crypto_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_universe_env(monkeypatch)
    monkeypatch.setenv("MODE", "backtest")
    monkeypatch.setenv("ASSET_UNIVERSE", "crypto")
    monkeypatch.setenv("STOCK_UNIVERSE", "SPY,QQQ")
    monkeypatch.setenv("CRYPTO_UNIVERSE", "btcusd,ethusd")

    settings = Settings.from_env()

    assert settings.symbols == ["BTCUSD", "ETHUSD"]


def test_settings_from_env_combines_universes_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_universe_env(monkeypatch)
    monkeypatch.setenv("MODE", "backtest")
    monkeypatch.setenv("ASSET_UNIVERSE", "all")
    monkeypatch.setenv("STOCK_UNIVERSE", "SPY,BTCUSD")
    monkeypatch.setenv("CRYPTO_UNIVERSE", "BTCUSD,ETHUSD")

    settings = Settings.from_env()

    assert settings.symbols == ["SPY", "BTCUSD", "ETHUSD"]


def test_settings_from_env_symbols_override_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("algotrade.config.load_dotenv", lambda *args, **kwargs: None)
    _clear_universe_env(monkeypatch)
    monkeypatch.setenv("MODE", "backtest")
    monkeypatch.setenv("SYMBOLS", "aapl,dogeusd")
    monkeypatch.setenv("ASSET_UNIVERSE", "crypto")
    monkeypatch.setenv("STOCK_UNIVERSE", "SPY")
    monkeypatch.setenv("CRYPTO_UNIVERSE", "BTCUSD")

    settings = Settings.from_env()

    assert settings.symbols == ["AAPL", "DOGEUSD"]

"""Tests for dynamic strategy loading."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.strategy.loader import available_strategies, create_strategy
from app.utils.errors import ConfigError


def test_create_strategy_uses_discovered_module() -> None:
    settings = Settings(alpaca_api_key="k", alpaca_secret_key="s", strategy="sma_crossover")
    strategy = create_strategy(name="sma_crossover", settings=settings)
    assert strategy.__class__.__name__ == "SmaCrossoverStrategy"


def test_create_strategy_rejects_unknown_name() -> None:
    settings = Settings(alpaca_api_key="k", alpaca_secret_key="s")
    with pytest.raises(ConfigError):
        create_strategy(name="does_not_exist", settings=settings)


def test_available_strategies_includes_defaults() -> None:
    names = available_strategies()
    assert "sma_crossover" in names
    assert "hft_pulse" in names

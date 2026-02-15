"""Tests for runtime credential requirements."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.main import validate_runtime_requirements
from app.utils.errors import ConfigError


def test_csv_backtest_does_not_require_keys() -> None:
    settings = Settings(
        alpaca_api_key="",
        alpaca_secret_key="",
        data_source="csv",
    )
    validate_runtime_requirements(settings=settings, backtest_mode=True)


def test_live_mode_requires_alpaca_keys() -> None:
    settings = Settings(
        alpaca_api_key="",
        alpaca_secret_key="",
        data_source="csv",
    )
    with pytest.raises(ConfigError):
        validate_runtime_requirements(settings=settings, backtest_mode=False)


def test_backtest_requires_explicit_csv_source() -> None:
    settings = Settings(
        alpaca_api_key="k",
        alpaca_secret_key="s",
        data_source="alpaca",
    )
    with pytest.raises(ConfigError):
        validate_runtime_requirements(settings=settings, backtest_mode=True)

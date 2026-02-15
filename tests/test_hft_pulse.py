"""Tests for the toy HFT pulse strategy."""

from __future__ import annotations

import pandas as pd

from app.strategy.base import Signal
from app.strategy.hft_pulse import HftPulseParams, HftPulseStrategy


def _bars_from_prices(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": prices})


def test_hft_pulse_alternates_when_market_is_flat() -> None:
    strategy = HftPulseStrategy(
        HftPulseParams(
            momentum_window=3,
            volatility_window=5,
            min_volatility=0.001,
            flip_seconds=2,
        )
    )
    bars = _bars_from_prices([100.0] * 30)

    signal_1 = strategy.generate_signal("SPY", bars)
    signal_2 = strategy.generate_signal("SPY", bars)
    signal_3 = strategy.generate_signal("SPY", bars)
    assert signal_1 == Signal.BUY
    assert signal_2 == Signal.SELL
    assert signal_3 == Signal.BUY


def test_hft_pulse_follows_positive_momentum() -> None:
    strategy = HftPulseStrategy(
        HftPulseParams(
            momentum_window=3,
            volatility_window=5,
            min_volatility=0.0,
            flip_seconds=3,
        )
    )
    bars = _bars_from_prices(
        [
            100.0,
            101.0,
            102.0,
            103.5,
            104.5,
            106.0,
            108.0,
            110.0,
            113.0,
            116.0,
            120.0,
            124.0,
        ]
    )
    signal = strategy.generate_signal("SPY", bars)
    assert signal == Signal.BUY

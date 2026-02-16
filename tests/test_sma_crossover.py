"""Minimal tests for the example strategy."""

from __future__ import annotations

import pandas as pd

from app.strategy.base import Signal
from app.strategy.sma_crossover import SmaCrossoverParams, SmaCrossoverStrategy


def test_returns_hold_when_not_enough_data() -> None:
    strategy = SmaCrossoverStrategy(SmaCrossoverParams(short_window=3, long_window=5))
    bars = pd.DataFrame({"close": [1, 2, 3, 4, 5]})

    signal = strategy.generate_signal(symbol="SPY", bars=bars)
    assert signal == Signal.HOLD


def test_initial_regime_emits_entry_after_warmup() -> None:
    strategy = SmaCrossoverStrategy(SmaCrossoverParams(short_window=2, long_window=3))
    bars = pd.DataFrame({"close": [1, 2, 3, 4]})

    signal = strategy.generate_signal(symbol="SPY", bars=bars)
    assert signal == Signal.BUY


def test_regime_flip_emits_opposite_signal() -> None:
    strategy = SmaCrossoverStrategy(SmaCrossoverParams(short_window=2, long_window=3))

    initial = pd.DataFrame({"close": [1, 2, 3, 4]})
    assert strategy.generate_signal(symbol="SPY", bars=initial) == Signal.BUY

    flipped = pd.DataFrame({"close": [1, 2, 3, 4, 2, 1]})
    assert strategy.generate_signal(symbol="SPY", bars=flipped) == Signal.SELL

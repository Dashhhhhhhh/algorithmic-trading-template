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


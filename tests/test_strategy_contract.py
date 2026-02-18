from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.momentum import MomentumParams, MomentumStrategy
from algotrade.strategies.scalping import ScalpingParams, ScalpingStrategy
from algotrade.strategies.sma_crossover import SmaCrossoverParams, SmaCrossoverStrategy


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(cash=1000.0, equity=1000.0, buying_power=1000.0, positions={})


def test_sma_crossover_returns_deterministic_targets() -> None:
    strategy = SmaCrossoverStrategy(SmaCrossoverParams(short_window=2, long_window=3, target_qty=1))
    uptrend = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]})
    downtrend = pd.DataFrame({"close": [4.0, 3.0, 2.0, 1.0]})

    up_targets = strategy.decide_targets({"SPY": uptrend}, _snapshot())
    down_targets = strategy.decide_targets({"SPY": downtrend}, _snapshot())

    assert up_targets == {"SPY": 1}
    assert down_targets == {"SPY": -1}


def test_momentum_returns_deterministic_sized_targets() -> None:
    strategy = MomentumStrategy(MomentumParams(lookback_bars=3, threshold=0.01, max_abs_qty=2))
    bullish = pd.DataFrame({"close": [100.0, 101.0, 102.0, 104.0, 106.0]})
    bearish = pd.DataFrame({"close": [106.0, 104.0, 103.0, 102.0, 100.0]})

    bullish_targets = strategy.decide_targets({"SPY": bullish}, _snapshot())
    bearish_targets = strategy.decide_targets({"SPY": bearish}, _snapshot())

    assert bullish_targets == {"SPY": 2}
    assert bearish_targets == {"SPY": -2}


def test_scalping_returns_signal_based_target_when_move_exceeds_threshold() -> None:
    strategy = ScalpingStrategy(
        ScalpingParams(
            lookback_bars=2,
            threshold=0.0005,
            max_abs_qty=2,
            flip_seconds=1,
            allow_short=True,
        ),
        now_provider=lambda: datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )
    bullish = pd.DataFrame({"close": [100.0, 100.01, 100.12]})
    bearish = pd.DataFrame({"close": [100.12, 100.01, 100.0]})

    bullish_targets = strategy.decide_targets({"SPY": bullish}, _snapshot())
    bearish_targets = strategy.decide_targets({"SPY": bearish}, _snapshot())

    assert bullish_targets == {"SPY": 2}
    assert bearish_targets == {"SPY": -2}


def test_scalping_flips_direction_when_signal_is_flat() -> None:
    bars = pd.DataFrame({"close": [100.0, 100.0, 100.0]})
    bullish_flip = ScalpingStrategy(
        ScalpingParams(
            lookback_bars=2,
            threshold=0.05,
            max_abs_qty=1,
            flip_seconds=1,
            allow_short=False,
        ),
        now_provider=lambda: datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
    )
    bearish_flip = ScalpingStrategy(
        ScalpingParams(
            lookback_bars=2,
            threshold=0.05,
            max_abs_qty=1,
            flip_seconds=1,
            allow_short=False,
        ),
        now_provider=lambda: datetime(2026, 1, 1, 0, 0, 3, tzinfo=UTC),
    )

    bullish_targets = bullish_flip.decide_targets({"SPY": bars}, _snapshot())
    bearish_targets = bearish_flip.decide_targets({"SPY": bars}, _snapshot())

    assert bullish_targets == {"SPY": 1}
    assert bearish_targets == {"SPY": 0}

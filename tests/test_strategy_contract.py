from __future__ import annotations

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.arbitrage import ArbitrageParams, ArbitrageStrategy
from algotrade.strategies.cross_sectional_momentum import (
    CrossSectionalMomentumParams,
    CrossSectionalMomentumStrategy,
)
from algotrade.strategies.scalping import ScalpingParams, ScalpingStrategy


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(cash=1000.0, equity=1000.0, buying_power=1000.0, positions={})


def test_scalping_returns_long_when_fast_ema_is_above_slow_and_rsi_is_not_overbought() -> None:
    strategy = ScalpingStrategy(
        ScalpingParams(
            fast_ema_period=2,
            slow_ema_period=4,
            rsi_period=3,
            rsi_overbought=80,
            rsi_oversold=20,
            max_abs_qty=2,
            allow_short=True,
        )
    )
    bars = pd.DataFrame({"close": [100.0, 100.8, 100.6, 101.1, 100.7, 101.4]})

    targets = strategy.decide_targets({"SPY": bars}, _snapshot())

    assert targets == {"SPY": 2}


def test_scalping_returns_short_when_fast_ema_is_below_slow_and_rsi_is_not_oversold() -> None:
    strategy = ScalpingStrategy(
        ScalpingParams(
            fast_ema_period=2,
            slow_ema_period=4,
            rsi_period=3,
            rsi_overbought=80,
            rsi_oversold=10,
            max_abs_qty=2,
            allow_short=True,
        )
    )
    bars = pd.DataFrame({"close": [101.8, 101.4, 101.1, 100.6, 100.9, 100.3]})

    targets = strategy.decide_targets({"SPY": bars}, _snapshot())

    assert targets == {"SPY": -2}


def test_cross_sectional_momentum_ranks_winners_and_losers() -> None:
    strategy = CrossSectionalMomentumStrategy(
        CrossSectionalMomentumParams(
            lookback_bars=2,
            top_k=1,
            max_abs_qty=1.5,
            allow_short=True,
        )
    )
    bars = {
        "AAA": pd.DataFrame({"close": [100.0, 102.0, 104.0]}),
        "BBB": pd.DataFrame({"close": [100.0, 101.0, 102.0]}),
        "CCC": pd.DataFrame({"close": [100.0, 99.0, 98.0]}),
    }

    targets = strategy.decide_targets(bars, _snapshot())

    assert targets == {"AAA": 1.5, "BBB": 0.0, "CCC": -1.5}


def test_cross_sectional_momentum_respects_allow_short() -> None:
    strategy = CrossSectionalMomentumStrategy(
        CrossSectionalMomentumParams(
            lookback_bars=2,
            top_k=1,
            max_abs_qty=1.5,
            allow_short=False,
        )
    )
    bars = {
        "AAA": pd.DataFrame({"close": [100.0, 102.0, 104.0]}),
        "BBB": pd.DataFrame({"close": [100.0, 99.0, 98.0]}),
    }

    targets = strategy.decide_targets(bars, _snapshot())

    assert targets == {"AAA": 1.5, "BBB": 0.0}


def test_arbitrage_shorts_rich_leg_and_longs_cheap_leg_when_spread_is_wide() -> None:
    strategy = ArbitrageStrategy(
        ArbitrageParams(
            lookback_bars=5,
            entry_zscore=1.5,
            exit_zscore=0.25,
            max_abs_qty=2,
            allow_short=True,
        )
    )
    bars = {
        "AAA": pd.DataFrame({"close": [100.0, 100.2, 100.1, 100.3, 100.1, 120.0]}),
        "BBB": pd.DataFrame({"close": [100.0, 100.1, 100.2, 100.3, 100.1, 100.0]}),
        "CCC": pd.DataFrame({"close": [50.0, 50.1, 50.2, 50.3, 50.1, 50.0]}),
    }

    targets = strategy.decide_targets(bars, _snapshot())

    assert targets["AAA"] == -2
    assert targets["BBB"] == 2
    assert targets["CCC"] == 0.0


def test_arbitrage_stays_flat_when_shorting_is_disabled() -> None:
    strategy = ArbitrageStrategy(
        ArbitrageParams(
            lookback_bars=5,
            entry_zscore=1.5,
            exit_zscore=0.25,
            max_abs_qty=2,
            allow_short=False,
        )
    )
    bars = {
        "AAA": pd.DataFrame({"close": [100.0, 100.2, 100.1, 100.3, 100.1, 120.0]}),
        "BBB": pd.DataFrame({"close": [100.0, 100.1, 100.2, 100.3, 100.1, 100.0]}),
    }

    targets = strategy.decide_targets(bars, _snapshot())

    assert targets == {"AAA": 0.0, "BBB": 0.0}

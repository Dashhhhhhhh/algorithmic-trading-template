from __future__ import annotations

import pandas as pd
import pytest

from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategies.hourly_zscore_overlay import (
    HourlyZScoreOverlayParams,
    HourlyZScoreOverlayStrategy,
    default_hourly_zscore_overlay_params,
)
from algotrade.strategies.momentum import MomentumParams, MomentumStrategy
from algotrade.strategies.scalping import ScalpingParams, ScalpingStrategy
from algotrade.strategies.sma_crossover import SmaCrossoverParams, SmaCrossoverStrategy


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(cash=1000.0, equity=1000.0, buying_power=1000.0, positions={})


def _snapshot_with_position(symbol: str, qty: float) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions={symbol: Position(symbol=symbol, qty=qty)},
    )


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
            allow_short=True,
        )
    )
    bullish = pd.DataFrame({"close": [100.0, 100.2, 100.4, 100.7, 100.9, 101.2, 101.4, 101.7]})
    bearish = pd.DataFrame({"close": [101.7, 101.4, 101.2, 100.9, 100.7, 100.4, 100.2, 100.0]})

    bullish_targets = strategy.decide_targets({"SPY": bullish}, _snapshot())
    bearish_targets = strategy.decide_targets({"SPY": bearish}, _snapshot())

    assert bullish_targets == {"SPY": 2}
    assert bearish_targets == {"SPY": -2}

    exit_bullish_targets = strategy.decide_targets(
        {"SPY": bullish},
        _snapshot_with_position("SPY", 2),
    )
    exit_bearish_targets = strategy.decide_targets(
        {"SPY": bearish},
        _snapshot_with_position("SPY", -2),
    )

    assert exit_bullish_targets == {"SPY": 0}
    assert exit_bearish_targets == {"SPY": 0}


def test_scalping_returns_flat_when_signal_is_weak() -> None:
    bars = pd.DataFrame({"close": [100.0, 100.02, 100.01, 100.03, 100.02, 100.03, 100.02, 100.03]})
    strategy = ScalpingStrategy(
        ScalpingParams(
            lookback_bars=2,
            threshold=0.002,
            max_abs_qty=1,
            allow_short=False,
        )
    )

    targets = strategy.decide_targets({"SPY": bars}, _snapshot())

    assert targets == {"SPY": 0}


def test_hourly_zscore_overlay_fades_extreme_returns() -> None:
    strategy = HourlyZScoreOverlayStrategy(
        HourlyZScoreOverlayParams(
            lookback_bars=4,
            z_score_threshold=1.0,
            max_abs_qty=2,
            require_stationarity=False,
            allow_short=True,
        )
    )
    upside_extreme = pd.DataFrame({"close": [100.0, 100.1, 100.2, 100.3, 110.33]})
    downside_extreme = pd.DataFrame({"close": [100.0, 99.9, 99.8, 99.7, 89.73]})

    short_targets = strategy.decide_targets({"SPY": upside_extreme}, _snapshot())
    long_targets = strategy.decide_targets({"SPY": downside_extreme}, _snapshot())

    assert short_targets["SPY"] == pytest.approx(-1.5, rel=1e-6)
    assert long_targets["SPY"] == pytest.approx(1.5, rel=1e-6)


def test_hourly_zscore_overlay_respects_allow_short() -> None:
    strategy = HourlyZScoreOverlayStrategy(
        HourlyZScoreOverlayParams(
            lookback_bars=4,
            z_score_threshold=1.0,
            max_abs_qty=2,
            require_stationarity=False,
            allow_short=False,
        )
    )
    upside_extreme = pd.DataFrame({"close": [100.0, 100.1, 100.2, 100.3, 110.33]})

    targets = strategy.decide_targets({"SPY": upside_extreme}, _snapshot())

    assert targets == {"SPY": 0}


def test_hourly_zscore_overlay_defaults_do_not_require_stationarity() -> None:
    params = default_hourly_zscore_overlay_params()
    assert params.require_stationarity is False

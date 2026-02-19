from __future__ import annotations

import math

import pandas as pd

from algotrade.config import Settings
from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategy_core.registry import available_strategy_ids, create_strategy


def _snapshot(positions: dict[str, float] | None = None) -> PortfolioSnapshot:
    normalized_positions: dict[str, Position] = {}
    for symbol, qty in (positions or {}).items():
        normalized_positions[symbol] = Position(symbol=symbol, qty=float(qty))
    return PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions=normalized_positions,
    )


def _bars(seed: float, drift: float, rows: int = 120) -> pd.DataFrame:
    closes = [seed + (drift * i) + ((i % 5) - 2) * 0.05 for i in range(rows)]
    opens = [value - 0.2 for value in closes]
    highs = [value + 0.4 for value in closes]
    lows = [max(value - 0.4, 0.01) for value in closes]
    volumes = [1000.0 + float(i) for i in range(rows)]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _sample_bars_by_symbol(rows: int = 120) -> dict[str, pd.DataFrame]:
    return {
        "SPY": _bars(seed=100.0, drift=0.18, rows=rows),
        "QQQ": _bars(seed=200.0, drift=-0.04, rows=rows),
        "AAPL": _bars(seed=150.0, drift=0.09, rows=rows),
    }


def test_registered_strategies_return_finite_numeric_targets() -> None:
    bars_by_symbol = _sample_bars_by_symbol(rows=120)
    snapshot = _snapshot({"SPY": 1.0, "QQQ": -0.5})
    known_symbols = set(bars_by_symbol) | set(snapshot.positions)

    for strategy_id in available_strategy_ids():
        strategy = create_strategy(strategy_id, Settings(strategy=strategy_id))
        targets = strategy.decide_targets(bars_by_symbol, snapshot)

        assert isinstance(targets, dict), strategy_id
        assert set(targets).issubset(known_symbols), strategy_id
        for symbol, target in targets.items():
            assert symbol in known_symbols, strategy_id
            assert isinstance(target, (int, float)), strategy_id
            assert math.isfinite(float(target)), strategy_id


def test_registered_strategies_handle_short_history_without_crashing() -> None:
    bars_by_symbol = _sample_bars_by_symbol(rows=5)
    snapshot = _snapshot({"SPY": 1.0})

    for strategy_id in available_strategy_ids():
        strategy = create_strategy(strategy_id, Settings(strategy=strategy_id))
        targets = strategy.decide_targets(bars_by_symbol, snapshot)
        assert isinstance(targets, dict), strategy_id

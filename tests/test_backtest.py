"""Tests for simple backtest runner."""

from __future__ import annotations

import pandas as pd

from app.backtest import run_backtest_for_symbol
from app.strategy.base import Signal, Strategy


class _AlwaysBuyStrategy(Strategy):
    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        _ = symbol, bars
        return Signal.BUY


def test_backtest_executes_trades() -> None:
    bars = pd.DataFrame(
        {
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100, 101, 102, 103],
            "volume": [1000, 1000, 1000, 1000],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
    )

    result = run_backtest_for_symbol(
        symbol="SPY",
        bars=bars,
        strategy=_AlwaysBuyStrategy(),
        qty=1,
        allow_short=True,
        starting_cash=1000.0,
    )
    assert result.trades >= 1
    assert result.end_equity > 0


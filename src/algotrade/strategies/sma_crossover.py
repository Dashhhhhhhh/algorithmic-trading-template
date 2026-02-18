"""SMA crossover target-position strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.base import Strategy


@dataclass(frozen=True)
class SmaCrossoverParams:
    """Parameter set for SMA crossover."""

    short_window: int = 20
    long_window: int = 50
    target_qty: float = 1.0


def default_sma_crossover_params() -> SmaCrossoverParams:
    """Default SMA strategy configuration kept local to this module."""
    return SmaCrossoverParams()


class SmaCrossoverStrategy(Strategy):
    """Move between long, short, and flat by SMA regime."""

    strategy_id = "sma_crossover"

    def __init__(self, params: SmaCrossoverParams) -> None:
        if params.short_window <= 0 or params.long_window <= 0:
            raise ValueError("SMA windows must be positive")
        if params.short_window >= params.long_window:
            raise ValueError("short_window must be less than long_window")
        if params.target_qty <= 0:
            raise ValueError("target_qty must be positive")
        self.params = params

    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, float]:
        _ = portfolio_snapshot
        targets: dict[str, float] = {}
        for symbol, bars in sorted(bars_by_symbol.items()):
            targets[symbol] = self._target_for_symbol(bars)
        return targets

    def _target_for_symbol(self, bars: pd.DataFrame) -> float:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")
        min_rows = self.params.long_window + 1
        if len(bars) < min_rows:
            return 0
        close = bars["close"]
        short_sma = close.rolling(window=self.params.short_window).mean()
        long_sma = close.rolling(window=self.params.long_window).mean()
        current_short = float(short_sma.iloc[-1])
        current_long = float(long_sma.iloc[-1])
        if current_short > current_long:
            return self.params.target_qty
        if current_short < current_long:
            return -self.params.target_qty
        return 0

"""Simple momentum strategy with deterministic target sizing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.execution.sizing import momentum_to_target
from algotrade.strategies.base import Strategy


@dataclass(frozen=True)
class MomentumParams:
    """Parameter set for momentum strategy."""

    lookback_bars: int = 10
    threshold: float = 0.01
    max_abs_qty: int = 2


class MomentumStrategy(Strategy):
    """Target long on positive momentum and short on negative momentum."""

    strategy_id = "momentum"

    def __init__(self, params: MomentumParams) -> None:
        if params.lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")
        if params.max_abs_qty <= 0:
            raise ValueError("max_abs_qty must be positive")
        if params.threshold < 0:
            raise ValueError("threshold must be non-negative")
        self.params = params

    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, int]:
        _ = portfolio_snapshot
        targets: dict[str, int] = {}
        for symbol, bars in sorted(bars_by_symbol.items()):
            targets[symbol] = self._target_for_symbol(bars)
        return targets

    def _target_for_symbol(self, bars: pd.DataFrame) -> int:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")
        if len(bars) <= self.params.lookback_bars:
            return 0
        current_price = float(bars["close"].iloc[-1])
        reference_price = float(bars["close"].iloc[-1 - self.params.lookback_bars])
        if reference_price == 0:
            return 0
        momentum_score = (current_price - reference_price) / reference_price
        return momentum_to_target(
            momentum_score=momentum_score,
            max_abs_qty=self.params.max_abs_qty,
            threshold=self.params.threshold,
        )

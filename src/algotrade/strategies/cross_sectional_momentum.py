"""Textbook cross-sectional momentum strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.base import Strategy


@dataclass(frozen=True)
class CrossSectionalMomentumParams:
    """Parameter set for cross-sectional momentum."""

    lookback_bars: int = 20
    top_k: int = 1
    max_abs_qty: float = 1.0
    # Percentage points of equity per position target (0.10 = 0.10%).
    min_trade_size_pct: float = 0.05
    max_trade_size_pct: float = 0.10
    allow_short: bool = True


def default_cross_sectional_momentum_params() -> CrossSectionalMomentumParams:
    """Default cross-sectional momentum configuration kept local to this module."""
    return CrossSectionalMomentumParams()


class CrossSectionalMomentumStrategy(Strategy):
    """Long recent winners and optionally short recent losers."""

    strategy_id = "cross_sectional_momentum"

    def __init__(self, params: CrossSectionalMomentumParams) -> None:
        if params.lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")
        if params.top_k <= 0:
            raise ValueError("top_k must be positive")
        if params.max_abs_qty <= 0:
            raise ValueError("max_abs_qty must be positive")
        if params.min_trade_size_pct <= 0 or params.max_trade_size_pct <= 0:
            raise ValueError("trade size percentages must be positive")
        if params.min_trade_size_pct > params.max_trade_size_pct:
            raise ValueError("min_trade_size_pct must be <= max_trade_size_pct")
        if params.max_trade_size_pct > 100:
            raise ValueError("max_trade_size_pct must be <= 100")
        self.params = params

    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, float]:
        _ = portfolio_snapshot
        targets = {symbol: 0.0 for symbol in sorted(bars_by_symbol)}
        scores: list[tuple[str, float]] = []

        for symbol, bars in sorted(bars_by_symbol.items()):
            score = self._momentum_score(bars)
            if score is not None:
                scores.append((symbol, score))

        if not scores:
            return targets

        ranked = sorted(scores, key=lambda item: (item[1], item[0]))
        k = min(self.params.top_k, len(ranked))
        for symbol, _score in ranked[-k:]:
            targets[symbol] = self.params.max_abs_qty

        if self.params.allow_short:
            for symbol, _score in ranked[:k]:
                if targets[symbol] > 0:
                    continue
                targets[symbol] = -self.params.max_abs_qty

        return targets

    def _momentum_score(self, bars: pd.DataFrame) -> float | None:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")
        close = pd.to_numeric(bars["close"], errors="coerce").dropna()
        if len(close) <= self.params.lookback_bars:
            return None
        latest = float(close.iloc[-1])
        reference = float(close.iloc[-1 - self.params.lookback_bars])
        if reference == 0:
            return None
        return (latest - reference) / reference

"""Textbook statistical arbitrage strategy (pairs mean reversion)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategy_core.base import Strategy


@dataclass(frozen=True)
class ArbitrageParams:
    """Parameter set for simple pairs trading."""

    lookback_bars: int = 30
    entry_zscore: float = 2.0
    exit_zscore: float = 0.5
    max_abs_qty: float = 1.0
    # Percentage points of equity per position target (0.10 = 0.10%).
    min_trade_size_pct: float = 0.05
    max_trade_size_pct: float = 0.10
    allow_short: bool = True


def default_arbitrage_params() -> ArbitrageParams:
    """Default arbitrage configuration kept local to this module."""
    return ArbitrageParams()


class ArbitrageStrategy(Strategy):
    """Trade mean reversion in the log-price spread of two symbols."""

    strategy_id = "arbitrage"

    def __init__(self, params: ArbitrageParams) -> None:
        if params.lookback_bars <= 1:
            raise ValueError("lookback_bars must be greater than 1")
        if params.entry_zscore <= 0:
            raise ValueError("entry_zscore must be positive")
        if params.exit_zscore < 0:
            raise ValueError("exit_zscore must be non-negative")
        if params.exit_zscore >= params.entry_zscore:
            raise ValueError("exit_zscore must be smaller than entry_zscore")
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
        targets = {
            symbol: float(
                portfolio_snapshot.positions.get(symbol, Position(symbol=symbol, qty=0)).qty
            )
            for symbol in sorted(bars_by_symbol)
        }
        pair = self._pick_pair(bars_by_symbol)
        if pair is None:
            return targets

        symbol_a, symbol_b = pair
        zscore = self._spread_zscore(bars_by_symbol[symbol_a], bars_by_symbol[symbol_b])
        if zscore is None:
            return targets
        if abs(zscore) <= self.params.exit_zscore:
            targets[symbol_a] = 0.0
            targets[symbol_b] = 0.0
            return targets
        if not self.params.allow_short:
            return targets

        if zscore >= self.params.entry_zscore:
            targets[symbol_a] = -self.params.max_abs_qty
            targets[symbol_b] = self.params.max_abs_qty
        elif zscore <= -self.params.entry_zscore:
            targets[symbol_a] = self.params.max_abs_qty
            targets[symbol_b] = -self.params.max_abs_qty
        return targets

    def _pick_pair(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> tuple[str, str] | None:
        valid = [
            symbol
            for symbol in sorted(bars_by_symbol)
            if self._has_usable_close(bars_by_symbol[symbol])
        ]
        if len(valid) < 2:
            return None
        return valid[0], valid[1]

    def _has_usable_close(self, bars: pd.DataFrame) -> bool:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")
        close = pd.to_numeric(bars["close"], errors="coerce").dropna()
        return len(close) > self.params.lookback_bars

    def _spread_zscore(self, bars_a: pd.DataFrame, bars_b: pd.DataFrame) -> float | None:
        close_a = pd.to_numeric(bars_a["close"], errors="coerce").dropna()
        close_b = pd.to_numeric(bars_b["close"], errors="coerce").dropna()
        aligned = pd.concat([close_a, close_b], axis=1, join="inner").dropna()
        if len(aligned) <= self.params.lookback_bars:
            return None

        ratio = aligned.iloc[:, 0] / aligned.iloc[:, 1]
        ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna()
        if len(ratio) <= self.params.lookback_bars:
            return None

        spread = np.log(ratio)
        window = spread.iloc[-self.params.lookback_bars :]
        mean = float(window.mean())
        std = float(window.std(ddof=0))
        if std <= 0:
            return None
        return (float(spread.iloc[-1]) - mean) / std

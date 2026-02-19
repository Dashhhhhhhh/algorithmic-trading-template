"""Donchian Channel Breakout strategy (long/short on channel breakouts)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategy_core.base import Strategy


@dataclass(frozen=True)
class DonchianBreakoutParams:
    """Parameter set for Donchian Channel Breakout."""

    period: int = 20
    target_qty: float = 1.0
    allow_short: bool = False


def default_donchian_channel_breakout_params() -> DonchianBreakoutParams:
    """Default Donchian Channel Breakout configuration kept local to this module."""
    return DonchianBreakoutParams()


class DonchianBreakoutStrategy(Strategy):
    """Trade breakouts above upper band (long) and below lower band (short/flat)."""

    strategy_id = "donchian_channel_breakout"

    def __init__(self, params: DonchianBreakoutParams) -> None:
        if params.period <= 0:
            raise ValueError("period must be positive")
        if params.target_qty <= 0:
            raise ValueError("target_qty must be positive")
        self.params = params

    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, float]:
        targets: dict[str, float] = {}
        for symbol, bars in sorted(bars_by_symbol.items()):
            current_qty = float(
                portfolio_snapshot.positions.get(symbol, Position(symbol=symbol, qty=0)).qty
            )
            targets[symbol] = self._target_for_symbol(bars, current_qty)
        return targets

    def _target_for_symbol(self, bars: pd.DataFrame, current_qty: float) -> float:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")
        high = bars["high"] if "high" in bars.columns else bars["close"]
        low = bars["low"] if "low" in bars.columns else bars["close"]
        close = pd.to_numeric(bars["close"], errors="coerce").dropna()
        high = pd.to_numeric(high, errors="coerce").reindex(close.index).ffill().bfill()
        low = pd.to_numeric(low, errors="coerce").reindex(close.index).ffill().bfill()
        min_rows = self.params.period + 2
        if len(close) < min_rows:
            return current_qty
        upper = high.rolling(window=self.params.period).max()
        lower = low.rolling(window=self.params.period).min()
        prev_upper = float(upper.iloc[-2])
        prev_lower = float(lower.iloc[-2])
        current_price = float(close.iloc[-1])
        if current_price > prev_upper and current_qty <= 0:
            return self.params.target_qty
        if current_price < prev_lower:
            if self.params.allow_short and current_qty >= 0:
                return -self.params.target_qty
            if not self.params.allow_short and current_qty > 0:
                return 0.0
        return current_qty

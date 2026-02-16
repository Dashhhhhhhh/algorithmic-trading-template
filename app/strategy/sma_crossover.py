"""Simple moving-average crossover strategy."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

import pandas as pd

from app.strategy.base import Signal, Strategy
from app.utils.errors import StrategyError

if TYPE_CHECKING:
    from app.config import Settings

STRATEGY_NAME = "sma_crossover"


@dataclass(frozen=True)
class SmaCrossoverParams:
    """Configurable parameters for SMA crossover."""

    short_window: int = 20
    long_window: int = 50


class SmaCrossoverStrategy(Strategy):
    """BUY when short SMA crosses above long SMA; SELL on opposite cross."""

    def __init__(self, params: SmaCrossoverParams) -> None:
        if params.short_window >= params.long_window:
            raise StrategyError("short_window must be less than long_window.")
        self.params = params
        self.logger = logging.getLogger("algotrade.strategy.sma_crossover")
        self._last_regime_by_symbol: dict[str, int] = {}

    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        required = {"close"}
        if not required.issubset(bars.columns):
            raise StrategyError(f"{symbol}: input bars must include 'close' column.")

        min_rows = self.params.long_window + 1
        if len(bars) < min_rows:
            self.logger.debug(
                "%s: not enough rows (%s) for SMA(%s/%s). Returning HOLD.",
                symbol,
                len(bars),
                self.params.short_window,
                self.params.long_window,
            )
            return Signal.HOLD

        close = bars["close"]
        short_sma = close.rolling(window=self.params.short_window).mean()
        long_sma = close.rolling(window=self.params.long_window).mean()

        prev_short, curr_short = short_sma.iloc[-2], short_sma.iloc[-1]
        prev_long, curr_long = long_sma.iloc[-2], long_sma.iloc[-1]

        if pd.isna(curr_short) or pd.isna(curr_long):
            return Signal.HOLD

        if curr_short > curr_long:
            current_regime = 1
        elif curr_short < curr_long:
            current_regime = -1
        else:
            current_regime = 0

        symbol_key = symbol.upper()
        last_regime = self._last_regime_by_symbol.get(symbol_key)
        if last_regime is None:
            # Initialize to the current regime so a fresh run can participate
            # in the active trend after warm-up.
            if current_regime != 0:
                self._last_regime_by_symbol[symbol_key] = current_regime
                return Signal.BUY if current_regime > 0 else Signal.SELL
            return Signal.HOLD

        if pd.isna(prev_short) or pd.isna(prev_long):
            if current_regime != 0:
                self._last_regime_by_symbol[symbol_key] = current_regime
            return Signal.HOLD

        if prev_short <= prev_long and curr_short > curr_long:
            self._last_regime_by_symbol[symbol_key] = 1
            return Signal.BUY
        if prev_short >= prev_long and curr_short < curr_long:
            self._last_regime_by_symbol[symbol_key] = -1
            return Signal.SELL

        if current_regime != 0:
            self._last_regime_by_symbol[symbol_key] = current_regime
        return Signal.HOLD


def build_strategy(settings: Settings) -> Strategy:
    """Build strategy instance from app settings."""
    params = SmaCrossoverParams(
        short_window=settings.sma_short_window,
        long_window=settings.sma_long_window,
    )
    return SmaCrossoverStrategy(params=params)

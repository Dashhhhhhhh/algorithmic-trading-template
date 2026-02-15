"""Toy HFT-style strategy intended for demos, not production trading."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

import pandas as pd

from app.strategy.base import Signal, Strategy
from app.utils.errors import StrategyError

if TYPE_CHECKING:
    from app.config import Settings

STRATEGY_NAME = "hft_pulse"


@dataclass(frozen=True)
class HftPulseParams:
    """Parameters for the toy HFT pulse strategy."""

    momentum_window: int = 3
    volatility_window: int = 12
    min_volatility: float = 0.0005
    flip_seconds: int = 3


class HftPulseStrategy(Strategy):
    """Fast-flipping demo strategy.

    How it works:
    - If recent momentum is strong, follow momentum (BUY on positive, SELL on negative).
    - If momentum is weak/flat, alternate BUY/SELL based on clock buckets.

    Club extension idea: replace clock-bias logic with real intraday tick features.
    """

    def __init__(self, params: HftPulseParams) -> None:
        if params.momentum_window <= 0 or params.volatility_window <= 0:
            raise StrategyError("HFT windows must be positive.")
        if params.flip_seconds <= 0:
            raise StrategyError("flip_seconds must be positive.")
        if params.min_volatility < 0:
            raise StrategyError("min_volatility cannot be negative.")
        self.params = params
        self.logger = logging.getLogger("algotrade.strategy.hft_pulse")
        self._last_signal_by_symbol: dict[str, Signal] = {}

    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        if "close" not in bars.columns:
            raise StrategyError(f"{symbol}: input bars must include 'close' column.")

        min_rows = max(self.params.momentum_window, self.params.volatility_window) + 2
        if len(bars) < min_rows:
            self.logger.info(
                "%s: not enough rows (%s) for HFT pulse min_rows=%s. Returning HOLD.",
                symbol,
                len(bars),
                min_rows,
            )
            return Signal.HOLD

        returns = bars["close"].pct_change().dropna()
        momentum = float(returns.tail(self.params.momentum_window).mean())
        volatility = float(returns.tail(self.params.volatility_window).std(ddof=0))

        if pd.isna(momentum) or pd.isna(volatility):
            return Signal.HOLD

        weak_momentum = abs(momentum) <= (volatility * 0.15)
        symbol_key = symbol.upper()

        if volatility < self.params.min_volatility or weak_momentum:
            # For "entertaining" demo behavior, alternate direction each pass
            # when the market regime is weak/flat.
            previous = self._last_signal_by_symbol.get(symbol_key, Signal.SELL)
            signal = Signal.BUY if previous == Signal.SELL else Signal.SELL
            reason = "alternating_bias"
        else:
            signal = Signal.BUY if momentum > 0 else Signal.SELL
            reason = "momentum"

        self._last_signal_by_symbol[symbol_key] = signal
        self.logger.info(
            "%s: hft_pulse signal=%s reason=%s momentum=%.6f vol=%.6f",
            symbol,
            signal.value,
            reason,
            momentum,
            volatility,
        )
        return signal


def build_strategy(settings: Settings) -> Strategy:
    """Build strategy instance from app settings."""
    params = HftPulseParams(
        momentum_window=settings.hft_momentum_window,
        volatility_window=settings.hft_volatility_window,
        min_volatility=settings.hft_min_volatility,
        flip_seconds=settings.hft_flip_seconds,
    )
    return HftPulseStrategy(params=params)

"""Toy HFT-style strategy intended for demos, not production trading."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import pandas as pd

from app.strategy.base import Signal, Strategy
from app.utils.errors import StrategyError


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

        clock_bucket = int(time.time() // self.params.flip_seconds)
        clock_bias = Signal.BUY if (clock_bucket % 2 == 0) else Signal.SELL
        weak_momentum = abs(momentum) <= (volatility * 0.15)

        if volatility < self.params.min_volatility or weak_momentum:
            signal = clock_bias
            reason = "clock_bias"
        else:
            signal = Signal.BUY if momentum > 0 else Signal.SELL
            reason = "momentum"

        self.logger.info(
            "%s: hft_pulse signal=%s reason=%s momentum=%.6f vol=%.6f bucket=%s",
            symbol,
            signal.value,
            reason,
            momentum,
            volatility,
            clock_bucket,
        )
        return signal


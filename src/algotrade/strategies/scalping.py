"""High-frequency scalping strategy with optional fast flip mode."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.base import Strategy


@dataclass(frozen=True)
class ScalpingParams:
    """Parameter set for high-frequency scalping strategy."""

    lookback_bars: int = 2
    threshold: float = 0.05
    max_abs_qty: int = 1
    flip_seconds: int = 1
    allow_short: bool = False


class ScalpingStrategy(Strategy):
    """Short-horizon momentum with optional timed side flips for stress testing."""

    strategy_id = "scalping"

    def __init__(
        self,
        params: ScalpingParams,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if params.lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")
        if params.max_abs_qty <= 0:
            raise ValueError("max_abs_qty must be positive")
        if params.threshold < 0:
            raise ValueError("threshold must be non-negative")
        if params.flip_seconds < 0:
            raise ValueError("flip_seconds must be non-negative")
        self.params = params
        self._now_provider = now_provider or (lambda: datetime.now(tz=UTC))

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

        latest_close = float(bars["close"].iloc[-1])
        reference_close = float(bars["close"].iloc[-1 - self.params.lookback_bars])
        if reference_close == 0:
            return 0

        short_return = (latest_close - reference_close) / reference_close
        direction = self._signal_direction(short_return)
        if direction < 0 and not self.params.allow_short:
            return 0
        return direction * self.params.max_abs_qty

    def _signal_direction(self, short_return: float) -> int:
        if short_return > 0 and short_return >= self.params.threshold:
            return 1
        if short_return < 0 and short_return <= -self.params.threshold:
            return -1
        return self._flip_direction()

    def _flip_direction(self) -> int:
        if self.params.flip_seconds <= 0:
            return 0
        now = self._now_provider()
        time_bucket = int(now.timestamp()) // self.params.flip_seconds
        return 1 if time_bucket % 2 == 0 else -1

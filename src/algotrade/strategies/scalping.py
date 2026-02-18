"""EMA + momentum scalping strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategies.base import Strategy


@dataclass(frozen=True)
class ScalpingParams:
    """Parameter set for a standard momentum scalping strategy."""

    lookback_bars: int = 2
    threshold: float = 0.00005
    max_abs_qty: float = 1.0
    # Percentage points of equity per position target (0.10 = 0.10%).
    min_trade_size_pct: float = 0.05
    max_trade_size_pct: float = 0.10
    # Legacy no-op retained for backward-compatible env parsing.
    flip_seconds: int = 1
    allow_short: bool = False


def default_scalping_params() -> ScalpingParams:
    """Default scalping strategy configuration kept local to this module."""
    return ScalpingParams()


class ScalpingStrategy(Strategy):
    """Scalp with fast/slow EMA trend plus short-horizon momentum confirmation."""

    strategy_id = "scalping"
    _POSITION_EPSILON = 1e-6

    def __init__(self, params: ScalpingParams) -> None:
        if params.lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")
        if params.max_abs_qty <= 0:
            raise ValueError("max_abs_qty must be positive")
        if params.threshold < 0:
            raise ValueError("threshold must be non-negative")
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
        targets: dict[str, float] = {}
        for symbol, bars in sorted(bars_by_symbol.items()):
            current_qty = portfolio_snapshot.positions.get(
                symbol,
                Position(symbol=symbol, qty=0.0),
            ).qty
            targets[symbol] = self._target_for_symbol(bars, current_qty=float(current_qty))
        return targets

    def _target_for_symbol(self, bars: pd.DataFrame, current_qty: float) -> float:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")

        fast_span = max(2, self.params.lookback_bars)
        slow_span = max(fast_span + 1, fast_span * 3)
        min_rows = max(self.params.lookback_bars + 1, slow_span + 1)
        if len(bars) < min_rows:
            return 0

        close = pd.to_numeric(bars["close"], errors="coerce").dropna()
        if len(close) < min_rows:
            return 0

        latest_close = float(close.iloc[-1])
        reference_close = float(close.iloc[-1 - self.params.lookback_bars])
        if reference_close == 0:
            return 0

        fast_ema = float(close.ewm(span=fast_span, adjust=False).mean().iloc[-1])
        slow_ema = float(close.ewm(span=slow_span, adjust=False).mean().iloc[-1])
        momentum = (latest_close - reference_close) / reference_close

        if fast_ema > slow_ema and momentum >= self.params.threshold:
            return self._cycle_target(current_qty=current_qty, entry_target=self.params.max_abs_qty)
        if fast_ema < slow_ema and momentum <= -self.params.threshold:
            if self.params.allow_short:
                return self._cycle_target(
                    current_qty=current_qty,
                    entry_target=-self.params.max_abs_qty,
                )
            return 0
        return 0

    def _cycle_target(self, current_qty: float, entry_target: float) -> float:
        """Alternate entry and exit so active signals naturally produce buy/sell cycles."""
        if entry_target > 0 and current_qty > self._POSITION_EPSILON:
            return 0.0
        if entry_target < 0 and current_qty < -self._POSITION_EPSILON:
            return 0.0
        return entry_target

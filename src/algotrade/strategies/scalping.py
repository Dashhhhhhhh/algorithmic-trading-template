"""Textbook scalping strategy (EMA trend + RSI filter)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.base import Strategy

try:  # pragma: no cover - optional acceleration when TA-Lib is installed.
    import talib as _talib
except ImportError:  # pragma: no cover - fallback path used in tests/CI.
    _talib = None


@dataclass(frozen=True)
class ScalpingParams:
    """Parameter set for EMA/RSI scalping."""

    fast_ema_period: int = 5
    slow_ema_period: int = 20
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    max_abs_qty: float = 1.0
    # Percentage points of equity per position target (0.10 = 0.10%).
    min_trade_size_pct: float = 0.05
    max_trade_size_pct: float = 0.10
    allow_short: bool = False


def default_scalping_params() -> ScalpingParams:
    """Default scalping strategy configuration kept local to this module."""
    return ScalpingParams()


class ScalpingStrategy(Strategy):
    """Trade fast trend shifts with EMA crossover confirmed by RSI."""

    strategy_id = "scalping"

    def __init__(self, params: ScalpingParams) -> None:
        if params.fast_ema_period <= 1 or params.slow_ema_period <= 1:
            raise ValueError("EMA periods must be greater than 1")
        if params.fast_ema_period >= params.slow_ema_period:
            raise ValueError("fast_ema_period must be less than slow_ema_period")
        if params.rsi_period <= 1:
            raise ValueError("rsi_period must be greater than 1")
        if not (0 <= params.rsi_oversold < params.rsi_overbought <= 100):
            raise ValueError("RSI thresholds must satisfy 0 <= oversold < overbought <= 100")
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
        targets: dict[str, float] = {}
        for symbol, bars in sorted(bars_by_symbol.items()):
            targets[symbol] = self._target_for_symbol(bars)
        return targets

    def _target_for_symbol(self, bars: pd.DataFrame) -> float:
        if "close" not in bars.columns:
            raise ValueError("bars must include close column")
        close = pd.to_numeric(bars["close"], errors="coerce").dropna()
        min_rows = max(self.params.slow_ema_period, self.params.rsi_period) + 1
        if len(close) < min_rows:
            return 0.0

        fast_ema, slow_ema, rsi = self._latest_indicators(close)
        if fast_ema is None or slow_ema is None or rsi is None:
            return 0.0
        if fast_ema > slow_ema and rsi < self.params.rsi_overbought:
            return self.params.max_abs_qty
        if self.params.allow_short and fast_ema < slow_ema and rsi > self.params.rsi_oversold:
            return -self.params.max_abs_qty
        return 0.0

    def _latest_indicators(
        self,
        close: pd.Series,
    ) -> tuple[float | None, float | None, float | None]:
        values = close.astype(float)
        if _talib is not None:
            raw = values.to_numpy()
            fast_ema = _to_float(_talib.EMA(raw, timeperiod=self.params.fast_ema_period)[-1])
            slow_ema = _to_float(_talib.EMA(raw, timeperiod=self.params.slow_ema_period)[-1])
            rsi = _to_float(_talib.RSI(raw, timeperiod=self.params.rsi_period)[-1])
            return fast_ema, slow_ema, rsi

        fast_ema_series = values.ewm(span=self.params.fast_ema_period, adjust=False).mean()
        slow_ema_series = values.ewm(span=self.params.slow_ema_period, adjust=False).mean()
        fast_ema = _to_float(fast_ema_series.iloc[-1])
        slow_ema = _to_float(slow_ema_series.iloc[-1])
        delta = values.diff()
        gains = delta.clip(lower=0.0)
        losses = -delta.clip(upper=0.0)
        avg_gain = gains.rolling(window=self.params.rsi_period).mean().iloc[-1]
        avg_loss = losses.rolling(window=self.params.rsi_period).mean().iloc[-1]
        if pd.isna(avg_gain) or pd.isna(avg_loss):
            return fast_ema, slow_ema, None
        if float(avg_loss) == 0:
            return fast_ema, slow_ema, 100.0
        rs = float(avg_gain) / float(avg_loss)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return fast_ema, slow_ema, rsi


def _to_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)

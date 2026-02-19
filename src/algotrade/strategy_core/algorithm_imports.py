"""Lean-style compatibility shim for pasted QCAlgorithm strategy snippets.

This module intentionally exposes symbols via ``from AlgorithmImports import *``.
The registry aliases this module to ``AlgorithmImports`` before loading strategies.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategy_core.base import Strategy


class Resolution:
    """Minimal resolution constants used by pasted QCAlgorithm code."""

    DAILY = "daily"
    HOUR = "hour"
    MINUTE = "minute"


@dataclass(frozen=True)
class _IndicatorPoint:
    value: float


class _IndicatorLine:
    def __init__(self) -> None:
        self._previous = 0.0
        self._current = 0.0

    @property
    def previous(self) -> _IndicatorPoint:
        return _IndicatorPoint(value=self._previous)

    @property
    def current(self) -> _IndicatorPoint:
        return _IndicatorPoint(value=self._current)

    def update(self, previous: float, current: float) -> None:
        self._previous = float(previous)
        self._current = float(current)


@dataclass(frozen=True)
class TradeBar:
    """Latest trade-bar snapshot exposed in ``data.bars``."""

    open: float
    high: float
    low: float
    close: float
    volume: float


class Slice:
    """Lean-like data slice containing per-symbol latest bars."""

    def __init__(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> None:
        bars: dict[str, TradeBar] = {}
        for symbol, frame in bars_by_symbol.items():
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            close = _coerce_float(latest.get("close"))
            if close is None:
                continue
            open_price = _coerce_float(latest.get("open"), default=close)
            high = _coerce_float(latest.get("high"), default=close)
            low = _coerce_float(latest.get("low"), default=close)
            volume = _coerce_float(latest.get("volume"), default=0.0)
            bars[symbol.upper()] = TradeBar(
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        self.bars = bars

    def __contains__(self, symbol: str) -> bool:
        return symbol.strip().upper() in self.bars

    def __getitem__(self, symbol: str) -> TradeBar:
        return self.bars[symbol.strip().upper()]


@dataclass(frozen=True)
class _Holdings:
    qty: float

    @property
    def is_long(self) -> bool:
        return self.qty > 0

    @property
    def is_short(self) -> bool:
        return self.qty < 0


class Security:
    """Lean-like security object with live price and holdings accessors."""

    def __init__(self, algorithm: QCAlgorithm, symbol: str) -> None:
        self._algorithm = algorithm
        self.symbol = symbol.strip().upper()

    @property
    def price(self) -> float:
        return self._algorithm._latest_prices.get(self.symbol, 0.0)

    @property
    def holdings(self) -> _Holdings:
        qty = self._algorithm._current_positions.get(self.symbol, 0.0)
        return _Holdings(qty=qty)


class _BaseIndicator:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.strip().upper()

    def update(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> None:
        raise NotImplementedError


class DonchianChannel(_BaseIndicator):
    def __init__(self, symbol: str, upper_period: int, lower_period: int) -> None:
        if upper_period <= 0 or lower_period <= 0:
            raise ValueError("Donchian periods must be positive")
        super().__init__(symbol)
        self.upper_period = int(upper_period)
        self.lower_period = int(lower_period)
        self.upper_band = _IndicatorLine()
        self.lower_band = _IndicatorLine()

    def update(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> None:
        frame = bars_by_symbol.get(self.symbol)
        if frame is None or frame.empty:
            return
        high_source = frame["high"] if "high" in frame.columns else frame["close"]
        low_source = frame["low"] if "low" in frame.columns else frame["close"]
        high = pd.to_numeric(high_source, errors="coerce")
        low = pd.to_numeric(low_source, errors="coerce")
        upper = high.rolling(window=self.upper_period).max()
        lower = low.rolling(window=self.lower_period).min()
        upper_prev, upper_cur = _previous_and_current(upper)
        lower_prev, lower_cur = _previous_and_current(lower)
        self.upper_band.update(previous=upper_prev, current=upper_cur)
        self.lower_band.update(previous=lower_prev, current=lower_cur)


class SimpleMovingAverage(_BaseIndicator):
    def __init__(self, symbol: str, period: int) -> None:
        if period <= 0:
            raise ValueError("SMA period must be positive")
        super().__init__(symbol)
        self.period = int(period)
        self.current = _IndicatorLine()

    def update(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> None:
        frame = bars_by_symbol.get(self.symbol)
        if frame is None or frame.empty or "close" not in frame.columns:
            return
        close = pd.to_numeric(frame["close"], errors="coerce")
        sma = close.rolling(window=self.period).mean()
        previous, current = _previous_and_current(sma)
        self.current.update(previous=previous, current=current)


class ExponentialMovingAverage(_BaseIndicator):
    def __init__(self, symbol: str, period: int) -> None:
        if period <= 0:
            raise ValueError("EMA period must be positive")
        super().__init__(symbol)
        self.period = int(period)
        self.current = _IndicatorLine()

    def update(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> None:
        frame = bars_by_symbol.get(self.symbol)
        if frame is None or frame.empty or "close" not in frame.columns:
            return
        close = pd.to_numeric(frame["close"], errors="coerce")
        ema = close.ewm(span=self.period, adjust=False).mean()
        previous, current = _previous_and_current(ema)
        self.current.update(previous=previous, current=current)


class RelativeStrengthIndex(_BaseIndicator):
    def __init__(self, symbol: str, period: int) -> None:
        if period <= 0:
            raise ValueError("RSI period must be positive")
        super().__init__(symbol)
        self.period = int(period)
        self.current = _IndicatorLine()

    def update(self, bars_by_symbol: Mapping[str, pd.DataFrame]) -> None:
        frame = bars_by_symbol.get(self.symbol)
        if frame is None or frame.empty or "close" not in frame.columns:
            return
        close = pd.to_numeric(frame["close"], errors="coerce")
        delta = close.diff()
        gains = delta.clip(lower=0.0)
        losses = -delta.clip(upper=0.0)
        avg_gain = gains.rolling(window=self.period).mean()
        avg_loss = losses.rolling(window=self.period).mean()
        rs = avg_gain / avg_loss.replace(0.0, pd.NA)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi = rsi.fillna(100.0)
        previous, current = _previous_and_current(rsi)
        self.current.update(previous=previous, current=current)


class QCAlgorithm:
    """Subset of Lean QCAlgorithm API used by copy/paste strategy snippets."""

    def __init__(self) -> None:
        self.settings = SimpleNamespace(automatic_indicator_warm_up=False)
        self.end_date: date = datetime.now(tz=UTC).date()
        self._start_date: date | None = None
        self._cash: float = 0.0
        self._securities: dict[str, Security] = {}
        self._indicators: dict[tuple[Any, ...], _BaseIndicator] = {}
        self._latest_prices: dict[str, float] = {}
        self._current_positions: dict[str, float] = {}
        self._bars_by_symbol: dict[str, pd.DataFrame] = {}
        self._targets: dict[str, float] = {}
        self._target_qty_scale: float = 1.0

    def set_start_date(self, start_date: date) -> None:
        self._start_date = start_date

    def set_cash(self, amount: float) -> None:
        self._cash = float(amount)

    def add_equity(self, ticker: str, resolution: str = Resolution.DAILY) -> Security:
        _ = resolution
        return self._add_security(ticker)

    def add_crypto(self, ticker: str, resolution: str = Resolution.DAILY) -> Security:
        _ = resolution
        return self._add_security(ticker)

    def dch(self, asset: Security | str, upper_period: int, lower_period: int) -> DonchianChannel:
        symbol = self._resolve_symbol(asset)
        key = ("dch", symbol, int(upper_period), int(lower_period))
        return self._get_or_create_indicator(
            key,
            lambda: DonchianChannel(
                symbol=symbol,
                upper_period=upper_period,
                lower_period=lower_period,
            ),
        )

    def sma(self, asset: Security | str, period: int) -> SimpleMovingAverage:
        symbol = self._resolve_symbol(asset)
        key = ("sma", symbol, int(period))
        return self._get_or_create_indicator(
            key,
            lambda: SimpleMovingAverage(symbol=symbol, period=period),
        )

    def ema(self, asset: Security | str, period: int) -> ExponentialMovingAverage:
        symbol = self._resolve_symbol(asset)
        key = ("ema", symbol, int(period))
        return self._get_or_create_indicator(
            key,
            lambda: ExponentialMovingAverage(symbol=symbol, period=period),
        )

    def rsi(self, asset: Security | str, period: int) -> RelativeStrengthIndex:
        symbol = self._resolve_symbol(asset)
        key = ("rsi", symbol, int(period))
        return self._get_or_create_indicator(
            key,
            lambda: RelativeStrengthIndex(symbol=symbol, period=period),
        )

    def set_holdings(self, asset: Security | str, weight: float) -> None:
        symbol = self._resolve_symbol(asset)
        target = float(weight) * self._target_qty_scale
        self._targets[symbol] = target

    def liquidate(self, asset: Security | str | None = None) -> None:
        if asset is None:
            for symbol in self._bars_by_symbol:
                self._targets[symbol] = 0.0
            return
        symbol = self._resolve_symbol(asset)
        self._targets[symbol] = 0.0

    def history(
        self,
        asset: Security | str,
        bar_count: int,
        resolution: str = Resolution.DAILY,
    ) -> pd.DataFrame:
        _ = resolution
        symbol = self._resolve_symbol(asset)
        frame = self._bars_by_symbol.get(symbol)
        if frame is None:
            return pd.DataFrame()
        if bar_count <= 0:
            return frame.iloc[0:0].copy()
        return frame.tail(int(bar_count)).copy()

    def plot(self, chart: str, series: str, value: float) -> None:
        _ = (chart, series, value)

    def debug(self, message: str) -> None:
        _ = message

    def log(self, message: str) -> None:
        _ = message

    def error(self, message: str) -> None:
        _ = message

    def _add_security(self, ticker: str) -> Security:
        symbol = ticker.strip().upper()
        if not symbol:
            raise ValueError("Ticker symbol cannot be empty")
        existing = self._securities.get(symbol)
        if existing is not None:
            return existing
        security = Security(self, symbol)
        self._securities[symbol] = security
        return security

    def _resolve_symbol(self, asset: Security | str) -> str:
        if isinstance(asset, Security):
            return asset.symbol
        if isinstance(asset, str):
            symbol = asset.strip().upper()
            if not symbol:
                raise ValueError("Symbol cannot be empty")
            return symbol
        symbol = str(getattr(asset, "symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("Asset must be a Security or symbol string")
        return symbol

    def _get_or_create_indicator(
        self,
        key: tuple[Any, ...],
        factory: Callable[[], _BaseIndicator],
    ) -> Any:
        indicator = self._indicators.get(key)
        if indicator is None:
            indicator = factory()
            self._indicators[key] = indicator
        return indicator

    def _prepare_cycle(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
        target_qty_scale: float,
    ) -> None:
        self._target_qty_scale = float(target_qty_scale)
        self._bars_by_symbol = {
            symbol.strip().upper(): frame.copy() for symbol, frame in bars_by_symbol.items()
        }
        self._current_positions = {
            symbol.strip().upper(): float(position.qty)
            for symbol, position in portfolio_snapshot.positions.items()
        }
        self._latest_prices = {}
        for symbol, frame in self._bars_by_symbol.items():
            if "close" not in frame.columns or frame.empty:
                continue
            close = pd.to_numeric(frame["close"], errors="coerce").dropna()
            if close.empty:
                continue
            self._latest_prices[symbol] = float(close.iloc[-1])
        self._targets = {}
        for indicator in self._indicators.values():
            indicator.update(self._bars_by_symbol)

    def _resolve_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, float]:
        targets: dict[str, float] = {}
        symbols = sorted({*bars_by_symbol.keys(), *portfolio_snapshot.positions.keys()})
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            current_qty = float(
                portfolio_snapshot.positions.get(symbol, Position(symbol=symbol, qty=0)).qty
            )
            targets[symbol] = self._targets.get(symbol, current_qty)
        for symbol, target in sorted(self._targets.items()):
            targets.setdefault(symbol, target)
        return targets


class QCAlgorithmStrategyAdapter(Strategy):
    """Adapter that runs a pasted QCAlgorithm class under the target-position contract."""

    strategy_id = "qc_algorithm"

    def __init__(
        self,
        algorithm_type: type[QCAlgorithm],
        strategy_id: str,
        target_qty_scale: float = 1.0,
    ) -> None:
        if target_qty_scale <= 0:
            raise ValueError("target_qty_scale must be positive")
        self.strategy_id = strategy_id
        self.algorithm_type = algorithm_type
        self.target_qty_scale = float(target_qty_scale)
        self.algorithm = algorithm_type()
        self._call_initialize()

    def _call_initialize(self) -> None:
        initialize = getattr(self.algorithm, "initialize", None)
        if callable(initialize):
            initialize()
            return
        alt_initialize = getattr(self.algorithm, "Initialize", None)
        if callable(alt_initialize):
            alt_initialize()

    def _call_on_data(self, data: Slice) -> None:
        on_data = getattr(self.algorithm, "on_data", None)
        if callable(on_data):
            on_data(data)
            return
        alt_on_data = getattr(self.algorithm, "OnData", None)
        if callable(alt_on_data):
            alt_on_data(data)

    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, float]:
        self.algorithm._prepare_cycle(
            bars_by_symbol=bars_by_symbol,
            portfolio_snapshot=portfolio_snapshot,
            target_qty_scale=self.target_qty_scale,
        )
        self._call_on_data(Slice(bars_by_symbol))
        return self.algorithm._resolve_targets(bars_by_symbol, portfolio_snapshot)


def _coerce_float(value: Any, default: float | None = None) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return default
    return float(parsed)


def _previous_and_current(series: pd.Series) -> tuple[float, float]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return 0.0, 0.0
    current = float(numeric.iloc[-1])
    previous = current if len(numeric) == 1 else float(numeric.iloc[-2])
    return previous, current


__all__ = [
    "QCAlgorithm",
    "QCAlgorithmStrategyAdapter",
    "Resolution",
    "Security",
    "Slice",
    "TradeBar",
    "timedelta",
]

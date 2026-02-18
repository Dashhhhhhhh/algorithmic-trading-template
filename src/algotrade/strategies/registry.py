"""Strategy registry for stable strategy selection."""

from __future__ import annotations

from collections.abc import Callable

from algotrade.config import Settings
from algotrade.strategies.base import Strategy
from algotrade.strategies.momentum import MomentumParams, MomentumStrategy
from algotrade.strategies.scalping import ScalpingParams, ScalpingStrategy
from algotrade.strategies.sma_crossover import SmaCrossoverParams, SmaCrossoverStrategy

StrategyFactory = Callable[[Settings], Strategy]


def _build_sma(settings: Settings) -> Strategy:
    return SmaCrossoverStrategy(
        params=SmaCrossoverParams(
            short_window=settings.sma_short_window,
            long_window=settings.sma_long_window,
            target_qty=settings.order_qty,
        )
    )


def _build_momentum(settings: Settings) -> Strategy:
    return MomentumStrategy(
        params=MomentumParams(
            lookback_bars=settings.momentum_lookback_bars,
            threshold=settings.momentum_threshold,
            max_abs_qty=settings.momentum_max_abs_qty,
        )
    )


def _build_scalping(settings: Settings) -> Strategy:
    return ScalpingStrategy(
        params=ScalpingParams(
            lookback_bars=settings.scalping_lookback_bars,
            threshold=settings.scalping_threshold,
            max_abs_qty=settings.scalping_max_abs_qty,
            flip_seconds=settings.scalping_flip_seconds,
            allow_short=settings.scalping_allow_short,
        )
    )


REGISTRY: dict[str, StrategyFactory] = {
    "sma_crossover": _build_sma,
    "momentum": _build_momentum,
    "scalping": _build_scalping,
}


def available_strategy_ids() -> list[str]:
    """Return supported strategy ids."""
    return sorted(REGISTRY.keys())


def create_strategy(strategy_id: str, settings: Settings) -> Strategy:
    """Build strategy instance from stable id."""
    normalized = strategy_id.strip().lower().replace("-", "_")
    factory = REGISTRY.get(normalized)
    if factory is None:
        supported = ", ".join(available_strategy_ids())
        raise ValueError(f"Unknown strategy '{strategy_id}'. Supported: {supported}")
    return factory(settings)

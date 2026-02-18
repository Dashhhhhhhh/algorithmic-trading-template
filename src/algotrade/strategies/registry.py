"""Strategy registry for stable strategy selection."""

from __future__ import annotations

from collections.abc import Callable

from algotrade.config import Settings
from algotrade.strategies.base import Strategy
from algotrade.strategies.momentum import (
    MomentumStrategy,
    default_momentum_params,
)
from algotrade.strategies.scalping import (
    ScalpingStrategy,
    default_scalping_params,
)
from algotrade.strategies.sma_crossover import (
    SmaCrossoverStrategy,
    default_sma_crossover_params,
)

StrategyFactory = Callable[[Settings], Strategy]


def _build_sma(settings: Settings) -> Strategy:
    _ = settings
    return SmaCrossoverStrategy(params=default_sma_crossover_params())


def _build_momentum(settings: Settings) -> Strategy:
    _ = settings
    return MomentumStrategy(params=default_momentum_params())


def _build_scalping(settings: Settings) -> Strategy:
    _ = settings
    return ScalpingStrategy(params=default_scalping_params())


REGISTRY: dict[str, StrategyFactory] = {
    "sma_crossover": _build_sma,
    "momentum": _build_momentum,
    "scalping": _build_scalping,
}
DEFAULT_STRATEGY_ID = "sma_crossover"


def available_strategy_ids() -> list[str]:
    """Return supported strategy ids."""
    return sorted(REGISTRY.keys())


def default_strategy_id() -> str:
    """Return the default strategy id resolved from the registry."""
    if DEFAULT_STRATEGY_ID in REGISTRY:
        return DEFAULT_STRATEGY_ID
    ids = available_strategy_ids()
    if not ids:
        raise ValueError("No strategies are registered")
    return ids[0]


def create_strategy(strategy_id: str, settings: Settings) -> Strategy:
    """Build strategy instance from stable id."""
    candidate = strategy_id.strip() or default_strategy_id()
    normalized = candidate.lower().replace("-", "_")
    factory = REGISTRY.get(normalized)
    if factory is None:
        supported = ", ".join(available_strategy_ids())
        raise ValueError(f"Unknown strategy '{strategy_id}'. Supported: {supported}")
    return factory(settings)

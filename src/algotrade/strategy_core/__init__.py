"""Shared strategy infrastructure (contract, registry, Lean adapter)."""

from .base import Strategy, StrategyInput
from .registry import available_strategy_ids, create_strategy, default_strategy_id

__all__ = [
    "Strategy",
    "StrategyInput",
    "available_strategy_ids",
    "create_strategy",
    "default_strategy_id",
]

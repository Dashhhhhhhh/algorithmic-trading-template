"""Dynamic strategy discovery and instantiation."""

from __future__ import annotations

from collections.abc import Callable
import importlib
import pkgutil
from types import ModuleType

from app.config import Settings
from app.strategy.base import Strategy
from app.utils.errors import ConfigError

StrategyFactory = Callable[[Settings], Strategy]
_SKIP_MODULES = {"base", "loader"}


def _iter_strategy_modules() -> list[ModuleType]:
    strategy_package = importlib.import_module("app.strategy")
    modules: list[ModuleType] = []
    for module_info in pkgutil.iter_modules(strategy_package.__path__):
        module_name = module_info.name
        if module_name.startswith("_") or module_name in _SKIP_MODULES:
            continue
        modules.append(importlib.import_module(f"app.strategy.{module_name}"))
    return modules


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def _registry() -> dict[str, StrategyFactory]:
    registry: dict[str, StrategyFactory] = {}
    for module in _iter_strategy_modules():
        factory = getattr(module, "build_strategy", None)
        if not callable(factory):
            continue
        strategy_name = _normalize_name(getattr(module, "STRATEGY_NAME", module.__name__.rsplit(".", 1)[-1]))
        registry[strategy_name] = factory
    return registry


def available_strategies() -> list[str]:
    """Return discovered strategy names."""
    return sorted(_registry().keys())


def create_strategy(name: str, settings: Settings) -> Strategy:
    """Instantiate a strategy from discovered strategy modules."""
    strategy_name = _normalize_name(name)
    registry = _registry()
    factory = registry.get(strategy_name)
    if factory is None:
        supported = ", ".join(sorted(registry)) or "none"
        raise ConfigError(
            f"Unknown strategy '{name}'. Discovered strategies: {supported}. "
            "Add/remove strategy modules in app/strategy and expose build_strategy(settings)."
        )
    strategy = factory(settings)
    if not isinstance(strategy, Strategy):
        raise ConfigError(
            f"Strategy '{strategy_name}' build_strategy(settings) must return Strategy."
        )
    return strategy

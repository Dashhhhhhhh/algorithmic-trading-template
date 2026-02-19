"""Strategy registry for stable strategy selection."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from algotrade.config import Settings
from algotrade.strategy_core import algorithm_imports
from algotrade.strategy_core.algorithm_imports import (
    QCAlgorithm,
    QCAlgorithmStrategyAdapter,
)
from algotrade.strategy_core.base import Strategy

StrategyFactory = Callable[[Settings], Strategy]
_SKIPPED_MODULES = {
    "__init__",
    "algorithm_imports",
    "base",
    "registry",
    "strategy_template",
}
DEFAULT_STRATEGY_ID = "scalping"
_STRATEGIES_PACKAGE_NAME = "algotrade.strategies"


def _strategies_package_name() -> str:
    return _STRATEGIES_PACKAGE_NAME


def _strategies_directory() -> Path:
    strategies_package = importlib.import_module(_strategies_package_name())
    package_paths = list(getattr(strategies_package, "__path__", []))
    if not package_paths:
        raise ValueError(f"Unable to resolve strategies package path: {_strategies_package_name()}")
    return Path(package_paths[0])


def _iter_strategy_module_names() -> list[str]:
    names: list[str] = []
    for module in pkgutil.iter_modules([str(_strategies_directory())]):
        name = module.name
        if name.startswith("_") or name in _SKIPPED_MODULES:
            continue
        names.append(name)
    return sorted(names)


def _normalize_strategy_id(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _resolved_strategy_id(module_name: str, candidate: type[Strategy]) -> str | None:
    raw = getattr(candidate, "strategy_id", None)
    if isinstance(raw, str):
        normalized = _normalize_strategy_id(raw)
        if normalized and normalized not in {"replace_me", "template"}:
            return normalized
    normalized_module_name = _normalize_strategy_id(module_name)
    if not normalized_module_name:
        return None
    return normalized_module_name


def _default_params_for(
    module: ModuleType,
    strategy_id: str,
) -> object | None:
    canonical_name = f"default_{_normalize_strategy_id(strategy_id)}_params"
    candidate = getattr(module, canonical_name, None)
    if callable(candidate):
        return candidate()

    fallbacks: list[Callable[[], object]] = []
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if function.__module__ != module.__name__:
            continue
        if name.startswith("default_") and name.endswith("_params"):
            fallbacks.append(function)
    if len(fallbacks) == 1:
        return fallbacks[0]()
    return None


def _ensure_algorithm_imports_alias() -> None:
    if "AlgorithmImports" in sys.modules:
        return
    sys.modules["AlgorithmImports"] = algorithm_imports


def _build_strategy(
    strategy_type: type[Strategy],
    module: ModuleType,
    settings: Settings,
    strategy_id: str,
) -> Strategy:
    signature = inspect.signature(strategy_type)
    kwargs: dict[str, object] = {}
    args: list[object] = []

    for parameter in signature.parameters.values():
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue

        if parameter.name == "settings":
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                args.append(settings)
            else:
                kwargs["settings"] = settings
            continue

        if parameter.name == "params":
            if parameter.default is not inspect.Signature.empty:
                continue
            params_object = _default_params_for(module, strategy_id)
            if params_object is None:
                raise ValueError(
                    f"Strategy '{strategy_id}' requires params but no "
                    "default_*_params() function was found."
                )
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                args.append(params_object)
            else:
                kwargs["params"] = params_object
            continue

        if parameter.default is inspect.Signature.empty:
            raise ValueError(
                f"Strategy '{strategy_id}' has unsupported required "
                f"constructor parameter '{parameter.name}'."
            )

    return strategy_type(*args, **kwargs)


def _strategy_types_in_module(module: ModuleType) -> list[tuple[type[Strategy], str]]:
    discovered: list[tuple[type[Strategy], str]] = []
    module_name = module.__name__.rsplit(".", 1)[-1]
    for _, candidate in inspect.getmembers(module, inspect.isclass):
        if candidate is Strategy or not issubclass(candidate, Strategy):
            continue
        if candidate.__module__ != module.__name__:
            continue
        strategy_id = _resolved_strategy_id(module_name, candidate)
        if strategy_id is None:
            continue
        discovered.append((candidate, strategy_id))
    return discovered


def _qc_algorithm_type_in_module(module: ModuleType) -> type[QCAlgorithm] | None:
    discovered: list[type[QCAlgorithm]] = []
    for _, candidate in inspect.getmembers(module, inspect.isclass):
        if candidate is QCAlgorithm or not issubclass(candidate, QCAlgorithm):
            continue
        if candidate.__module__ != module.__name__:
            continue
        discovered.append(candidate)
    if not discovered:
        return None
    if len(discovered) == 1:
        return discovered[0]
    names = ", ".join(sorted(item.__name__ for item in discovered))
    raise ValueError(
        f"Module '{module.__name__}' has multiple QCAlgorithm classes ({names}). "
        "Keep one per module for auto-registration."
    )


@lru_cache(maxsize=1)
def _discover_registry() -> tuple[dict[str, StrategyFactory], dict[str, str]]:
    _ensure_algorithm_imports_alias()
    package_name = _strategies_package_name()
    registry: dict[str, StrategyFactory] = {}
    load_errors: dict[str, str] = {}

    for module_name in _iter_strategy_module_names():
        import_path = f"{package_name}.{module_name}"
        try:
            module = importlib.import_module(import_path)
        except Exception as exc:  # pragma: no cover - defensive path
            load_errors[module_name] = f"{type(exc).__name__}: {exc}"
            continue

        discovered_strategy_types = _strategy_types_in_module(module)
        for strategy_type, strategy_id in discovered_strategy_types:
            if strategy_id in registry:
                raise ValueError(f"Duplicate strategy id discovered: '{strategy_id}'")

            def factory(
                settings: Settings,
                strategy_cls: type[Strategy] = strategy_type,
                strategy_module: ModuleType = module,
                resolved_id: str = strategy_id,
            ) -> Strategy:
                return _build_strategy(strategy_cls, strategy_module, settings, resolved_id)

            registry[strategy_id] = factory
        if discovered_strategy_types:
            continue

        module_strategy_id = _normalize_strategy_id(module_name)
        if not module_strategy_id:
            continue
        try:
            qc_algorithm_type = _qc_algorithm_type_in_module(module)
        except Exception as exc:  # pragma: no cover - defensive path
            load_errors[module_name] = f"{type(exc).__name__}: {exc}"
            continue
        if qc_algorithm_type is None:
            continue
        if module_strategy_id in registry:
            raise ValueError(f"Duplicate strategy id discovered: '{module_strategy_id}'")

        def qc_factory(
            settings: Settings,
            algorithm_type: type[QCAlgorithm] = qc_algorithm_type,
            strategy_id: str = module_strategy_id,
        ) -> Strategy:
            _ = settings
            return QCAlgorithmStrategyAdapter(
                algorithm_type=algorithm_type,
                strategy_id=strategy_id,
            )

        registry[module_strategy_id] = qc_factory

    return registry, load_errors


def available_strategy_ids() -> list[str]:
    """Return supported strategy ids."""
    registry, _ = _discover_registry()
    return sorted(registry.keys())


def default_strategy_id() -> str:
    """Return the default strategy id resolved from the registry."""
    registry, _ = _discover_registry()
    if DEFAULT_STRATEGY_ID in registry:
        return DEFAULT_STRATEGY_ID
    ids = available_strategy_ids()
    if not ids:
        raise ValueError("No strategies are registered")
    return ids[0]


def create_strategy(strategy_id: str, settings: Settings) -> Strategy:
    """Build strategy instance from stable id."""
    candidate = strategy_id.strip() or default_strategy_id()
    normalized = _normalize_strategy_id(candidate)
    registry, load_errors = _discover_registry()
    factory = registry.get(normalized)
    if factory is None:
        supported = ", ".join(available_strategy_ids())
        load_error = load_errors.get(normalized)
        if load_error is not None:
            raise ValueError(f"Strategy '{strategy_id}' could not be loaded: {load_error}")
        if load_errors:
            unavailable = ", ".join(sorted(load_errors))
            raise ValueError(
                f"Unknown strategy '{strategy_id}'. Supported: {supported}. "
                f"Unavailable modules: {unavailable}"
            )
        raise ValueError(f"Unknown strategy '{strategy_id}'. Supported: {supported}")
    return factory(settings)

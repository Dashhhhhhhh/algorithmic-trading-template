from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from algotrade.config import Settings
from algotrade.strategies.scalping import ScalpingStrategy
from algotrade.strategy_core import registry
from algotrade.strategy_core.base import Strategy
from algotrade.strategy_core.registry import available_strategy_ids, create_strategy


class _TemplatePlaceholderStrategy(Strategy):
    strategy_id = "template"

    def decide_targets(self, bars_by_symbol: Mapping[str, pd.DataFrame], portfolio_snapshot):
        _ = (bars_by_symbol, portfolio_snapshot)
        return {}


def test_registry_discovers_strategy_modules() -> None:
    strategy_ids = available_strategy_ids()

    assert "arbitrage" in strategy_ids
    assert "cross_sectional_momentum" in strategy_ids
    assert "scalping" in strategy_ids
    assert "sma_crossover" in strategy_ids
    assert len(strategy_ids) >= 4


def test_registry_accepts_hyphenated_strategy_id() -> None:
    strategy = create_strategy(
        "cross-sectional-momentum",
        Settings(strategy="cross_sectional_momentum"),
    )

    assert strategy.strategy_id == "cross_sectional_momentum"


def test_registry_resolves_template_placeholder_to_module_name() -> None:
    resolved = registry._resolved_strategy_id("my_custom_strategy", _TemplatePlaceholderStrategy)

    assert resolved == "my_custom_strategy"


def test_registry_keeps_explicit_strategy_id_when_not_placeholder() -> None:
    resolved = registry._resolved_strategy_id("scalping", ScalpingStrategy)

    assert resolved == "scalping"

from __future__ import annotations

from algotrade.config import Settings
from algotrade.strategies.registry import available_strategy_ids, create_strategy


def test_registry_discovers_strategy_modules() -> None:
    strategy_ids = available_strategy_ids()

    assert "arbitrage" in strategy_ids
    assert "cross_sectional_momentum" in strategy_ids
    assert "scalping" in strategy_ids
    assert len(strategy_ids) == 3


def test_registry_accepts_hyphenated_strategy_id() -> None:
    strategy = create_strategy(
        "cross-sectional-momentum",
        Settings(strategy="cross_sectional_momentum"),
    )

    assert strategy.strategy_id == "cross_sectional_momentum"

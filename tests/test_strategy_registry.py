from __future__ import annotations

from algotrade.config import Settings
from algotrade.strategies.registry import available_strategy_ids, create_strategy


def test_registry_discovers_strategy_modules() -> None:
    strategy_ids = available_strategy_ids()

    assert "sma_crossover" in strategy_ids
    assert "momentum" in strategy_ids
    assert "scalping" in strategy_ids
    assert "hourly_zscore_overlay" in strategy_ids


def test_registry_accepts_hyphenated_strategy_id() -> None:
    strategy = create_strategy(
        "hourly-zscore-overlay",
        Settings(strategy="hourly_zscore_overlay"),
    )

    assert strategy.strategy_id == "hourly_zscore_overlay"

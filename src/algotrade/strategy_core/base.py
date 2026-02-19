"""Strategy contract based on target positions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot


@dataclass(frozen=True)
class StrategyInput:
    """Container for strategy evaluation inputs."""

    bars_by_symbol: Mapping[str, pd.DataFrame]
    portfolio_snapshot: PortfolioSnapshot


class Strategy(ABC):
    """Base strategy interface."""

    strategy_id: str

    @abstractmethod
    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, float]:
        """Return target quantities by symbol."""

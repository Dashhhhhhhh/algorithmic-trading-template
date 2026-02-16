"""Template strategy implementation for quick copy-and-edit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot
from algotrade.strategies.base import Strategy


@dataclass(frozen=True)
class TemplateParams:
    """Example parameter dataclass for custom strategies."""

    target_qty: int = 1


class TemplateStrategy(Strategy):
    """Minimal strategy skeleton implementing the target contract."""

    strategy_id = "replace_me"

    def __init__(self, params: TemplateParams) -> None:
        self.params = params

    def decide_targets(
        self,
        bars_by_symbol: Mapping[str, pd.DataFrame],
        portfolio_snapshot: PortfolioSnapshot,
    ) -> dict[str, int]:
        _ = bars_by_symbol
        _ = portfolio_snapshot
        return {}

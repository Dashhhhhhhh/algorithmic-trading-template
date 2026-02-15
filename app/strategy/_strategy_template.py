"""Template for creating a new strategy module.

Usage:
1. Copy this file to `app/strategy/<your_strategy_name>.py`.
2. Set `STRATEGY_NAME` to match that module name.
3. Implement `generate_signal(...)` logic.
4. Wire any new env settings in `app/config.py` and map them in `build_strategy(...)`.

The loader discovers strategy files in `app/strategy/` that expose:
- `STRATEGY_NAME` (optional; filename is used if omitted)
- `build_strategy(settings) -> Strategy`
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from app.strategy.base import Signal, Strategy

if TYPE_CHECKING:
    from app.config import Settings

# Replace with your strategy key, e.g. "mean_reversion".
STRATEGY_NAME = "replace_me"


@dataclass(frozen=True)
class TemplateParams:
    """Example parameter container for your strategy."""

    lookback_window: int = 20


class TemplateStrategy(Strategy):
    """Minimal strategy skeleton. Replace with your implementation."""

    def __init__(self, params: TemplateParams) -> None:
        self.params = params

    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        # TODO: implement your signal logic.
        # Return one of: Signal.BUY, Signal.SELL, Signal.HOLD.
        _ = symbol
        _ = bars
        return Signal.HOLD


def build_strategy(settings: Settings) -> Strategy:
    """Factory function used by the dynamic strategy loader."""
    # Map values from `settings` into your params here.
    _ = settings
    params = TemplateParams()
    return TemplateStrategy(params=params)

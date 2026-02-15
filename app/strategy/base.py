"""Base strategy types and interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class Signal(str, Enum):
    """Supported directional signals for this starter project."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Strategy(ABC):
    """Abstract strategy interface.

    Club extension idea: return confidence scores or target position sizes
    instead of only BUY/SELL/HOLD.
    """

    @abstractmethod
    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        """Return BUY, SELL, or HOLD for a symbol."""


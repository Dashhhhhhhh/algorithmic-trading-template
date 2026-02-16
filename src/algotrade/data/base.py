"""Market data provider contract."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    """Interface for bar retrieval."""

    def get_bars(self, symbol: str) -> pd.DataFrame:
        """Return OHLCV bars with datetime index."""

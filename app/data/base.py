"""Data client interfaces used by execution and backtesting."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataClient(Protocol):
    """Protocol for market data providers."""

    def fetch_daily(self, symbol: str, adjusted: bool = False) -> pd.DataFrame:
        """Return OHLCV bars with datetime index and standard columns."""


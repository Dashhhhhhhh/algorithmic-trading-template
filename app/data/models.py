"""Typed data models for market data modules."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class HistoricalData:
    """Container for historical OHLCV bars for a single symbol."""

    symbol: str
    bars: pd.DataFrame


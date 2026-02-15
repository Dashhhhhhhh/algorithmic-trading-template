"""Typed models for Alpaca responses and requests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    """Supported order sides."""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class AccountInfo:
    """Minimal account fields used by the trader."""

    id: str
    status: str
    cash: float
    buying_power: float
    trading_blocked: bool


@dataclass(frozen=True)
class Position:
    """Minimal position model."""

    symbol: str
    qty: float
    side: str


@dataclass(frozen=True)
class OrderRequest:
    """Request model for market orders."""

    symbol: str
    qty: int
    side: OrderSide
    type: str = "market"
    time_in_force: str = "day"


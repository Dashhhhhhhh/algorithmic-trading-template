"""Core trading domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

Mode = Literal["backtest", "live"]


class OrderSide(StrEnum):
    """Supported order directions."""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Position:
    """Current signed position for a symbol."""

    symbol: str
    qty: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio state used by strategies and risk checks."""

    cash: float
    equity: float
    buying_power: float
    positions: dict[str, Position] = field(default_factory=dict)


@dataclass(frozen=True)
class Order:
    """Open order view returned by broker adapters."""

    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    status: str
    client_order_id: str | None = None


@dataclass(frozen=True)
class OrderRequest:
    """Order intent produced by the execution engine."""

    symbol: str
    qty: float
    side: OrderSide
    order_type: str = "market"
    time_in_force: str = "day"
    client_order_id: str | None = None


@dataclass(frozen=True)
class OrderReceipt:
    """Submission result returned by brokers."""

    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    status: str
    client_order_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskLimits:
    """Portfolio-level risk constraints."""

    max_abs_position_per_symbol: float = 100.0
    allow_short: bool = True

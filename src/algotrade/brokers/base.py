"""Broker contract definitions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from algotrade.domain.models import Order, OrderReceipt, OrderRequest, PortfolioSnapshot, Position


class Broker(Protocol):
    """Interface for live/backtest brokers."""

    def get_portfolio(self) -> PortfolioSnapshot:
        """Return current portfolio snapshot."""

    def get_positions(self) -> dict[str, Position]:
        """Return current positions keyed by symbol."""

    def get_open_orders(self) -> list[Order]:
        """Return currently open orders."""

    def submit_orders(self, requests: list[OrderRequest]) -> list[OrderReceipt]:
        """Submit orders and return receipts."""

    def subscribe_trade_updates(
        self,
        handler: Callable[[Order], None],
    ) -> None:
        """Optional trade update subscription."""

"""Deterministic in-memory broker for backtests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from algotrade.domain.models import (
    Order,
    OrderReceipt,
    OrderRequest,
    OrderSide,
    PortfolioSnapshot,
    Position,
)


@dataclass
class BacktestBroker:
    """Backtest broker that fills market orders immediately."""

    starting_cash: float = 100_000.0
    positions: dict[str, Position] = field(default_factory=dict)

    def get_portfolio(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            cash=self.starting_cash,
            equity=self.starting_cash,
            buying_power=self.starting_cash,
            positions=self.get_positions(),
        )

    def get_positions(self) -> dict[str, Position]:
        return dict(self.positions)

    def get_open_orders(self) -> list[Order]:
        return []

    def submit_orders(self, requests: list[OrderRequest]) -> list[OrderReceipt]:
        receipts: list[OrderReceipt] = []
        for request in requests:
            current = self.positions.get(request.symbol, Position(symbol=request.symbol, qty=0)).qty
            signed_delta = request.qty if request.side is OrderSide.BUY else -request.qty
            updated = current + signed_delta
            self.positions[request.symbol] = Position(symbol=request.symbol, qty=updated)
            receipts.append(
                OrderReceipt(
                    order_id=str(uuid4()),
                    symbol=request.symbol,
                    side=request.side,
                    qty=request.qty,
                    status="filled",
                    client_order_id=request.client_order_id,
                    raw={"source": "backtest"},
                )
            )
        return receipts

    def subscribe_trade_updates(self, handler: Callable[[Order], None]) -> None:
        _ = handler
        return None

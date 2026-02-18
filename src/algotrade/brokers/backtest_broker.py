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
    market_prices: dict[str, float] = field(default_factory=dict)
    cash: float = field(init=False)

    def __post_init__(self) -> None:
        self.cash = float(self.starting_cash)

    def get_portfolio(self) -> PortfolioSnapshot:
        market_value = 0.0
        for symbol, position in self.positions.items():
            price = self.market_prices.get(symbol)
            if price is None:
                continue
            market_value += float(position.qty) * float(price)
        equity = self.cash + market_value
        return PortfolioSnapshot(
            cash=self.cash,
            equity=equity,
            buying_power=self.cash,
            positions=self.get_positions(),
        )

    def get_positions(self) -> dict[str, Position]:
        return dict(self.positions)

    def get_open_orders(self) -> list[Order]:
        return []

    def submit_orders(self, requests: list[OrderRequest]) -> list[OrderReceipt]:
        receipts: list[OrderReceipt] = []
        for request in requests:
            fill_price = self.market_prices.get(request.symbol)
            if fill_price is None:
                raise ValueError(
                    f"No market price available for {request.symbol}. "
                    "Update backtest prices before submitting orders."
                )
            current = self.positions.get(request.symbol, Position(symbol=request.symbol, qty=0)).qty
            signed_delta = request.qty if request.side is OrderSide.BUY else -request.qty
            updated = current + signed_delta
            if request.side is OrderSide.BUY:
                self.cash -= fill_price * request.qty
            else:
                self.cash += fill_price * request.qty

            if updated == 0:
                self.positions.pop(request.symbol, None)
            else:
                self.positions[request.symbol] = Position(symbol=request.symbol, qty=updated)
            receipts.append(
                OrderReceipt(
                    order_id=str(uuid4()),
                    symbol=request.symbol,
                    side=request.side,
                    qty=request.qty,
                    status="filled",
                    client_order_id=request.client_order_id,
                    raw={"source": "backtest", "filled_avg_price": fill_price},
                )
            )
        return receipts

    def update_market_prices(self, prices: dict[str, float]) -> None:
        """Update symbol marks used for fills and mark-to-market equity."""
        for symbol, price in prices.items():
            self.market_prices[symbol] = float(price)

    def subscribe_trade_updates(self, handler: Callable[[Order], None]) -> None:
        _ = handler
        return None

"""Risk filters for outbound orders."""

from __future__ import annotations

from algotrade.domain.models import OrderRequest, OrderSide, PortfolioSnapshot, Position, RiskLimits


def filter_orders_by_limits(
    orders: list[OrderRequest],
    portfolio_snapshot: PortfolioSnapshot,
    limits: RiskLimits,
) -> list[OrderRequest]:
    """Filter orders that violate shorting or max-position constraints."""
    safe_orders: list[OrderRequest] = []
    for order in orders:
        current_qty = portfolio_snapshot.positions.get(
            order.symbol,
            Position(symbol=order.symbol, qty=0),
        ).qty
        signed_delta = order.qty if order.side is OrderSide.BUY else -order.qty
        proposed_qty = current_qty + signed_delta
        if not limits.allow_short and proposed_qty < 0:
            continue
        if abs(proposed_qty) > limits.max_abs_position_per_symbol:
            continue
        safe_orders.append(order)
    return safe_orders

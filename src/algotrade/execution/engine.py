"""Target-position execution helpers."""

from __future__ import annotations

from algotrade.domain.models import OrderRequest, OrderSide, PortfolioSnapshot, Position, RiskLimits
from algotrade.execution.risk import filter_orders_by_limits


def compute_orders(
    current_positions: dict[str, Position],
    targets: dict[str, int],
    default_order_type: str,
) -> list[OrderRequest]:
    """Translate current and target positions into delta orders."""
    orders: list[OrderRequest] = []
    for symbol, target_qty in sorted(targets.items()):
        current_qty = current_positions.get(symbol, Position(symbol=symbol, qty=0)).qty
        delta = int(target_qty) - int(current_qty)
        if delta == 0:
            continue
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        request = OrderRequest(
            symbol=symbol,
            qty=abs(delta),
            side=side,
            order_type=default_order_type,
        )
        orders.append(request)
    return orders


def apply_risk_gates(
    orders: list[OrderRequest],
    portfolio_snapshot: PortfolioSnapshot,
    limits: RiskLimits,
) -> list[OrderRequest]:
    """Apply risk checks and return submit-safe orders."""
    return filter_orders_by_limits(
        orders=orders,
        portfolio_snapshot=portfolio_snapshot,
        limits=limits,
    )

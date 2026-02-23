"""Target-position execution helpers."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from algotrade.domain.models import OrderRequest, OrderSide, PortfolioSnapshot, Position, RiskLimits
from algotrade.execution.risk import filter_orders_by_limits


def compute_orders(
    current_positions: dict[str, Position],
    targets: dict[str, float],
    default_order_type: str,
    min_trade_qty: float = 0.0001,
    qty_precision: int = 6,
) -> list[OrderRequest]:
    """Translate current and target positions into delta orders."""
    orders: list[OrderRequest] = []
    normalized_min_trade_qty = max(float(min_trade_qty), 1e-9)
    precision = max(0, int(qty_precision))
    for symbol, target_qty in sorted(targets.items()):
        current_qty = float(current_positions.get(symbol, Position(symbol=symbol, qty=0)).qty)
        delta = float(target_qty) - current_qty
        qty = _quantize_down(abs(delta), precision)
        if qty < normalized_min_trade_qty:
            continue
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        request = OrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=default_order_type,
        )
        orders.append(request)
    return orders


def _quantize_down(value: float, precision: int) -> float:
    """Round toward zero at fixed precision to avoid oversizing fractional orders."""
    if precision <= 0:
        quantum = Decimal("1")
    else:
        quantum = Decimal("1").scaleb(-precision)
    decimal_value = Decimal(str(max(value, 0.0)))
    quantized = decimal_value.quantize(quantum, rounding=ROUND_DOWN)
    return float(quantized)


def apply_risk_gates(
    orders: list[OrderRequest],
    portfolio_snapshot: PortfolioSnapshot,
    limits: RiskLimits,
    non_shortable_symbols: set[str] | None = None,
) -> list[OrderRequest]:
    """Apply risk checks and return submit-safe orders."""
    return filter_orders_by_limits(
        orders=orders,
        portfolio_snapshot=portfolio_snapshot,
        limits=limits,
        non_shortable_symbols=non_shortable_symbols,
    )

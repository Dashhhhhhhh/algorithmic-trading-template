"""Risk filters for outbound orders."""

from __future__ import annotations

from collections.abc import Iterable

from algotrade.domain.models import OrderRequest, OrderSide, PortfolioSnapshot, Position, RiskLimits


def filter_orders_by_limits(
    orders: list[OrderRequest],
    portfolio_snapshot: PortfolioSnapshot,
    limits: RiskLimits,
    non_shortable_symbols: set[str] | None = None,
) -> list[OrderRequest]:
    """Filter orders that violate shorting or max-position constraints."""
    blocked_short_symbols = _normalize_symbols(non_shortable_symbols)
    safe_orders: list[OrderRequest] = []
    for order in orders:
        current_qty = portfolio_snapshot.positions.get(
            order.symbol,
            Position(symbol=order.symbol, qty=0),
        ).qty
        signed_delta = order.qty if order.side is OrderSide.BUY else -order.qty
        proposed_qty = current_qty + signed_delta
        symbol_forbids_short = order.symbol.upper() in blocked_short_symbols
        if proposed_qty < 0 and (not limits.allow_short or symbol_forbids_short):
            continue
        if abs(proposed_qty) > limits.max_abs_position_per_symbol:
            continue
        safe_orders.append(order)
    return safe_orders


def _normalize_symbols(symbols: Iterable[str] | None) -> set[str]:
    if symbols is None:
        return set()
    normalized = set()
    for symbol in symbols:
        value = str(symbol).strip().upper()
        if value:
            normalized.add(value)
    return normalized

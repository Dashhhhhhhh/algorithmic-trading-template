from __future__ import annotations

from algotrade.domain.models import OrderSide, PortfolioSnapshot, Position, RiskLimits
from algotrade.execution.engine import apply_risk_gates, compute_orders


def test_compute_orders_flat_to_long() -> None:
    orders = compute_orders(
        current_positions={"SPY": Position(symbol="SPY", qty=0)},
        targets={"SPY": 3},
        default_order_type="market",
    )

    assert len(orders) == 1
    assert orders[0].symbol == "SPY"
    assert orders[0].side is OrderSide.BUY
    assert orders[0].qty == 3


def test_compute_orders_long_to_flat() -> None:
    orders = compute_orders(
        current_positions={"SPY": Position(symbol="SPY", qty=2)},
        targets={"SPY": 0},
        default_order_type="market",
    )

    assert len(orders) == 1
    assert orders[0].symbol == "SPY"
    assert orders[0].side is OrderSide.SELL
    assert orders[0].qty == 2


def test_apply_risk_gates_blocks_short_when_disabled() -> None:
    orders = compute_orders(
        current_positions={"SPY": Position(symbol="SPY", qty=0)},
        targets={"SPY": -1},
        default_order_type="market",
    )
    snapshot = PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions={"SPY": Position(symbol="SPY", qty=0)},
    )
    safe = apply_risk_gates(
        orders=orders,
        portfolio_snapshot=snapshot,
        limits=RiskLimits(max_abs_position_per_symbol=10, allow_short=False),
    )

    assert safe == []


def test_compute_orders_handles_fractional_deltas() -> None:
    orders = compute_orders(
        current_positions={"BTCUSD": Position(symbol="BTCUSD", qty=0.998)},
        targets={"BTCUSD": 0.0},
        default_order_type="market",
    )

    assert len(orders) == 1
    assert orders[0].symbol == "BTCUSD"
    assert orders[0].side is OrderSide.SELL
    assert orders[0].qty == 0.998

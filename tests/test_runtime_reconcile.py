from __future__ import annotations

from algotrade.domain.models import OrderRequest, OrderSide, PortfolioSnapshot, Position, RiskLimits
from algotrade.runtime import find_risk_blocked_orders, resolve_intent_status
from algotrade.state.store import OrderIntentRecord


def test_resolve_intent_status_marks_stale_when_not_open_and_not_filled() -> None:
    intent = OrderIntentRecord(
        client_order_id="cid-1",
        run_id="run-1",
        symbol="SPY",
        side="sell",
        qty=2,
        status="submitted",
        broker_order_id="oid-1",
        fingerprint="SPY|sell|2",
    )

    status = resolve_intent_status(
        intent=intent,
        open_client_ids=set(),
        positions={"SPY": Position(symbol="SPY", qty=1)},
    )

    assert status == "stale_reconciled"


def test_resolve_intent_status_prefers_broker_filled_status() -> None:
    intent = OrderIntentRecord(
        client_order_id="cid-1",
        run_id="run-1",
        symbol="BTCUSD",
        side="buy",
        qty=0.001037,
        status="submitted",
        broker_order_id="oid-1",
        fingerprint="BTCUSD|buy|0.001037",
    )

    status = resolve_intent_status(
        intent=intent,
        open_client_ids=set(),
        positions={"BTCUSD": Position(symbol="BTCUSD", qty=0.00103585)},
        broker_status="filled",
    )

    assert status == "filled_reconciled"


def test_resolve_intent_status_keeps_submitted_when_open() -> None:
    intent = OrderIntentRecord(
        client_order_id="cid-1",
        run_id="run-1",
        symbol="SPY",
        side="buy",
        qty=1,
        status="submitted",
        broker_order_id="oid-1",
        fingerprint="SPY|buy|1",
    )

    status = resolve_intent_status(
        intent=intent,
        open_client_ids={"cid-1"},
        positions={"SPY": Position(symbol="SPY", qty=0)},
    )

    assert status == "submitted"


def test_find_risk_blocked_orders_reports_short_disabled() -> None:
    raw_orders = [OrderRequest(symbol="SPY", qty=2, side=OrderSide.SELL)]
    safe_orders: list[OrderRequest] = []
    portfolio = PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions={"SPY": Position(symbol="SPY", qty=1)},
    )
    limits = RiskLimits(max_abs_position_per_symbol=10, allow_short=False)

    blocked = find_risk_blocked_orders(raw_orders, safe_orders, portfolio, limits)

    assert blocked == [
        {
            "symbol": "SPY",
            "side": "sell",
            "qty": 2,
            "current_qty": 1,
            "proposed_qty": -1,
            "reason": "short_disabled",
        }
    ]


def test_find_risk_blocked_orders_reports_asset_not_shortable() -> None:
    raw_orders = [OrderRequest(symbol="ETHUSD", qty=1, side=OrderSide.SELL)]
    safe_orders: list[OrderRequest] = []
    portfolio = PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions={"ETHUSD": Position(symbol="ETHUSD", qty=0)},
    )
    limits = RiskLimits(max_abs_position_per_symbol=10, allow_short=True)

    blocked = find_risk_blocked_orders(
        raw_orders,
        safe_orders,
        portfolio,
        limits,
        non_shortable_symbols={"ETHUSD"},
    )

    assert blocked == [
        {
            "symbol": "ETHUSD",
            "side": "sell",
            "qty": 1,
            "current_qty": 0,
            "proposed_qty": -1,
            "reason": "asset_not_shortable",
        }
    ]


def test_find_risk_blocked_orders_reports_fractional_short_unsupported() -> None:
    raw_orders = [OrderRequest(symbol="SPY", qty=0.4, side=OrderSide.SELL)]
    safe_orders: list[OrderRequest] = []
    portfolio = PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions={"SPY": Position(symbol="SPY", qty=0.2)},
    )
    limits = RiskLimits(max_abs_position_per_symbol=10, allow_short=True)

    blocked = find_risk_blocked_orders(raw_orders, safe_orders, portfolio, limits)

    assert blocked == [
        {
            "symbol": "SPY",
            "side": "sell",
            "qty": 0.4,
            "current_qty": 0.2,
            "proposed_qty": -0.2,
            "reason": "fractional_short_unsupported",
        }
    ]

"""Tests for open-order reconciliation before submit."""

from __future__ import annotations

from app.broker.models import OrderSide
from app.execution.trader import Trader


class _DummyBroker:
    def __init__(self, orders: list[dict]) -> None:
        self.orders = orders
        self.canceled: list[str] = []

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        return self.orders

    def cancel_order(self, order_id: str) -> None:
        self.canceled.append(order_id)


def _dummy_trader(broker: _DummyBroker) -> Trader:
    return Trader(
        data_client=object(),   # type: ignore[arg-type]
        broker_client=broker,   # type: ignore[arg-type]
        strategy=object(),      # type: ignore[arg-type]
        dry_run=True,
        default_qty=1,
    )


def test_prepare_open_orders_cancels_conflict_and_allows_submit() -> None:
    broker = _DummyBroker(
        orders=[
            {"id": "abc", "symbol": "SPY", "side": "buy"},
        ]
    )
    trader = _dummy_trader(broker)
    should_submit = trader._prepare_open_orders_for_symbol("SPY", OrderSide.SELL)
    assert should_submit is True
    assert broker.canceled == ["abc"]


def test_prepare_open_orders_skips_duplicate_same_side() -> None:
    broker = _DummyBroker(
        orders=[
            {"id": "abc", "symbol": "SPY", "side": "sell"},
        ]
    )
    trader = _dummy_trader(broker)
    should_submit = trader._prepare_open_orders_for_symbol("SPY", OrderSide.SELL)
    assert should_submit is False
    assert broker.canceled == []


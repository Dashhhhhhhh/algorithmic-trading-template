from __future__ import annotations

import pytest

from algotrade.config import Settings
from algotrade.domain.models import (
    OrderReceipt,
    OrderRequest,
    OrderSide,
    PortfolioSnapshot,
    Position,
)
from algotrade.runtime import build_liquidation_orders, liquidate


def test_build_liquidation_orders_flattens_longs_and_shorts() -> None:
    orders = build_liquidation_orders(
        positions={
            "TSLA": Position(symbol="TSLA", qty=3),
            "AAPL": Position(symbol="AAPL", qty=-2),
            "SPY": Position(symbol="SPY", qty=0),
        },
    )

    assert [(order.symbol, order.side, order.qty) for order in orders] == [
        ("AAPL", OrderSide.BUY, 2),
        ("TSLA", OrderSide.SELL, 3),
    ]


def test_build_liquidation_orders_uses_default_order_type() -> None:
    orders = build_liquidation_orders(
        positions={"SPY": Position(symbol="SPY", qty=1)},
        default_order_type="limit",
    )

    assert len(orders) == 1
    assert orders[0].order_type == "limit"


class StubBroker:
    def __init__(self, positions: dict[str, Position]) -> None:
        self._positions = positions
        self.submitted: list[OrderRequest] = []
        self.portfolio_calls = 0

    def get_positions(self) -> dict[str, Position]:
        return dict(self._positions)

    def get_portfolio(self) -> PortfolioSnapshot:
        self.portfolio_calls += 1
        return PortfolioSnapshot(cash=1234.56, equity=1234.56, buying_power=1234.56, positions={})

    def submit_orders(self, requests: list[OrderRequest]) -> list[OrderReceipt]:
        self.submitted = list(requests)
        return [
            OrderReceipt(
                order_id=f"oid-{request.symbol}",
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                status="accepted",
            )
            for request in requests
        ]


def test_liquidate_submits_flattening_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    broker = StubBroker(
        positions={
            "TSLA": Position(symbol="TSLA", qty=3),
            "AAPL": Position(symbol="AAPL", qty=-2),
        }
    )
    monkeypatch.setattr("algotrade.runtime.build_broker", lambda _settings: broker)

    exit_code = liquidate(Settings(mode="live"))

    assert exit_code == 0
    assert [(order.symbol, order.side, order.qty) for order in broker.submitted] == [
        ("AAPL", OrderSide.BUY, 2),
        ("TSLA", OrderSide.SELL, 3),
    ]
    assert broker.portfolio_calls == 1


def test_liquidate_requires_live_mode() -> None:
    with pytest.raises(ValueError, match="--liquidate requires --mode live"):
        liquidate(Settings(mode="backtest"))


class StubCloseAllBroker:
    def __init__(self) -> None:
        self.close_called = False
        self.submit_called = False
        self.portfolio_calls = 0

    def get_positions(self) -> dict[str, Position]:
        return {"BTCUSD": Position(symbol="BTCUSD", qty=1)}

    def get_portfolio(self) -> PortfolioSnapshot:
        self.portfolio_calls += 1
        return PortfolioSnapshot(cash=99.9, equity=99.9, buying_power=99.9, positions={})

    def close_all_positions(self, cancel_orders: bool = True) -> list[dict[str, object]]:
        self.close_called = cancel_orders
        return [{"id": "oid-1", "symbol": "BTCUSD", "qty": "0.997499995", "side": "sell"}]

    def submit_orders(self, requests: list[OrderRequest]) -> list[OrderReceipt]:
        self.submit_called = True
        return []


def test_liquidate_prefers_close_all_positions_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = StubCloseAllBroker()
    monkeypatch.setattr("algotrade.runtime.build_broker", lambda _settings: broker)

    exit_code = liquidate(Settings(mode="live"))

    assert exit_code == 0
    assert broker.close_called is True
    assert broker.submit_called is False
    assert broker.portfolio_calls == 1

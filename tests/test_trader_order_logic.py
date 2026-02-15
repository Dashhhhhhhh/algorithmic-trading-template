"""Unit tests for signal-to-order translation logic."""

from __future__ import annotations

from app.broker.models import OrderSide, Position
from app.execution.trader import Trader
from app.strategy.base import Signal


def test_sell_signal_opens_short_when_allowed() -> None:
    order = Trader._build_order(
        symbol="SPY",
        signal=Signal.SELL,
        current_qty=0,
        qty=1,
        allow_short=True,
    )
    assert order is not None
    assert order.side == OrderSide.SELL
    assert order.qty == 1


def test_sell_signal_flattens_when_shorting_disabled() -> None:
    order = Trader._build_order(
        symbol="SPY",
        signal=Signal.SELL,
        current_qty=2,
        qty=1,
        allow_short=False,
    )
    assert order is not None
    assert order.side == OrderSide.SELL
    assert order.qty == 2


def test_buy_signal_flips_short_to_long() -> None:
    order = Trader._build_order(
        symbol="SPY",
        signal=Signal.BUY,
        current_qty=-1,
        qty=1,
        allow_short=True,
    )
    assert order is not None
    assert order.side == OrderSide.BUY
    assert order.qty == 2


def test_signed_position_from_short_side() -> None:
    signed = Trader._signed_position_qty(Position(symbol="SPY", qty=3.0, side="short"))
    assert signed == -3


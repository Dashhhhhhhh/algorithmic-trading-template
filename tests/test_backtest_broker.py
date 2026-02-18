from __future__ import annotations

import pytest

from algotrade.brokers.backtest_broker import BacktestBroker
from algotrade.domain.models import OrderRequest, OrderSide


def test_backtest_broker_marks_to_market_for_long_position() -> None:
    broker = BacktestBroker(starting_cash=1000.0)
    broker.update_market_prices({"SPY": 100.0})

    receipts = broker.submit_orders([OrderRequest(symbol="SPY", qty=2, side=OrderSide.BUY)])
    after_fill = broker.get_portfolio()

    assert after_fill.cash == 800.0
    assert after_fill.equity == 1000.0
    assert after_fill.positions["SPY"].qty == 2
    assert receipts[0].raw["filled_avg_price"] == 100.0

    broker.update_market_prices({"SPY": 110.0})
    after_mark = broker.get_portfolio()

    assert after_mark.cash == 800.0
    assert after_mark.equity == 1020.0


def test_backtest_broker_marks_to_market_for_short_position() -> None:
    broker = BacktestBroker(starting_cash=1000.0)
    broker.update_market_prices({"SPY": 50.0})

    broker.submit_orders([OrderRequest(symbol="SPY", qty=1, side=OrderSide.SELL)])
    after_fill = broker.get_portfolio()
    assert after_fill.cash == 1050.0
    assert after_fill.equity == 1000.0
    assert after_fill.positions["SPY"].qty == -1

    broker.update_market_prices({"SPY": 40.0})
    after_mark = broker.get_portfolio()
    assert after_mark.cash == 1050.0
    assert after_mark.equity == 1010.0


def test_backtest_broker_requires_price_before_submission() -> None:
    broker = BacktestBroker(starting_cash=1000.0)

    with pytest.raises(ValueError, match="No market price available"):
        broker.submit_orders([OrderRequest(symbol="SPY", qty=1, side=OrderSide.BUY)])

from __future__ import annotations

import pandas as pd

from algotrade.domain.models import (
    OrderReceipt,
    OrderRequest,
    OrderSide,
    PortfolioSnapshot,
    Position,
)
from algotrade.runtime import (
    build_latest_prices,
    compute_equity_metrics,
    extract_receipt_price_details,
    serialize_orders,
    serialize_portfolio,
    serialize_positions,
    serialize_receipts,
    summarize_decision_details,
)


def test_summarize_decision_details_includes_price_return_and_delta() -> None:
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.0, 101.0, 103.0],
            "volume": [1000.0, 1100.0, 1200.0],
        },
        index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
    )

    details = summarize_decision_details(
        bars=bars,
        lookback_bars=2,
        target_qty=2,
        current_qty=-1,
    )

    assert details["delta_qty"] == 3
    assert details["bars"] == 3
    assert details["close"] == 103.0
    assert details["ret_1"] == 0.019802
    assert details["ret_lb"] == 0.03
    assert details["asof"] == "2025-01-03T00:00:00"
    assert details["volume"] == 1200.0


def test_serialize_helpers_emit_json_friendly_payloads() -> None:
    positions = {"SPY": Position(symbol="SPY", qty=2), "AAPL": Position(symbol="AAPL", qty=-1)}
    requests = [
        OrderRequest(symbol="SPY", qty=2, side=OrderSide.BUY),
    ]
    receipts = [
        OrderReceipt(
            order_id="oid-1",
            symbol="SPY",
            side=OrderSide.BUY,
            qty=2,
            status="filled",
            client_order_id="cid-1",
            raw={"source": "backtest"},
        )
    ]
    portfolio = PortfolioSnapshot(
        cash=100000.0,
        equity=100100.0,
        buying_power=99900.0,
        positions=positions,
    )

    assert serialize_positions(positions) == {"AAPL": -1, "SPY": 2}
    assert serialize_orders(requests) == [
        {
            "symbol": "SPY",
            "side": "buy",
            "qty": 2,
            "order_type": "market",
            "time_in_force": "day",
            "client_order_id": None,
        }
    ]
    assert serialize_receipts(receipts) == [
        {
            "order_id": "oid-1",
            "symbol": "SPY",
            "side": "buy",
            "qty": 2,
            "status": "filled",
            "client_order_id": "cid-1",
            "raw": {"source": "backtest"},
        }
    ]
    assert serialize_portfolio(portfolio) == {
        "cash": 100000.0,
        "equity": 100100.0,
        "buying_power": 99900.0,
        "positions": {"AAPL": -1, "SPY": 2},
    }


def test_build_latest_prices_and_equity_metrics() -> None:
    bars = pd.DataFrame(
        {
            "close": [100.0, 101.0],
        },
        index=pd.to_datetime(["2025-01-01", "2025-01-02"]),
    )
    prices = build_latest_prices({"SPY": bars})
    assert prices == {"SPY": 101.0}

    run_metrics: dict[str, float | None] = {"start_equity": None, "previous_equity": None}
    first = compute_equity_metrics(run_metrics, equity=1000.0)
    second = compute_equity_metrics(run_metrics, equity=1010.0)

    assert first == {"equity": 1000.0, "pnl_start": 0.0, "pnl_prev": 0.0, "pnl_start_pct": 0.0}
    assert second == {"equity": 1010.0, "pnl_start": 10.0, "pnl_prev": 10.0, "pnl_start_pct": 0.01}


def test_extract_receipt_price_details() -> None:
    receipt = OrderReceipt(
        order_id="oid-2",
        symbol="SPY",
        side=OrderSide.BUY,
        qty=2,
        status="filled",
        client_order_id="cid-2",
        raw={
            "filled_avg_price": "100.5",
            "limit_price": "101.2",
            "submitted_at": "2026-02-17T18:00:00Z",
        },
    )

    details = extract_receipt_price_details(receipt)

    assert details == {
        "filled_avg_price": 100.5,
        "filled_notional": 201.0,
        "limit_price": 101.2,
        "submitted_at": "2026-02-17T18:00:00Z",
    }

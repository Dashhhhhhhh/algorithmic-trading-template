from __future__ import annotations

import sqlite3
from pathlib import Path

from algotrade.domain.models import OrderRequest, OrderSide
from algotrade.state.sqlite_store import SqliteStateStore


def test_sqlite_store_persists_run_and_intended_orders(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = SqliteStateStore(str(db_path))
    store.record_run("run-1", "live", "scalping", ["SPY"])
    request = OrderRequest(
        symbol="SPY",
        qty=1,
        side=OrderSide.BUY,
        client_order_id="cid-1",
    )
    store.save_intended_order("run-1", request)
    store.close()

    reopened = SqliteStateStore(str(db_path))
    active = reopened.list_active_intents()

    assert len(active) == 1
    assert active[0].run_id == "run-1"
    assert active[0].client_order_id == "cid-1"
    assert reopened.has_active_intent("SPY", "buy", 1)

    reopened.mark_reconciled("cid-1", "filled_reconciled")
    assert not reopened.has_active_intent("SPY", "buy", 1)
    reopened.close()

    connection = sqlite3.connect(db_path)
    row = connection.execute(
        "SELECT run_id, mode, strategy_id FROM runs WHERE run_id='run-1'"
    ).fetchone()
    connection.close()

    assert row == ("run-1", "live", "scalping")


def test_sqlite_store_tracks_fractional_order_qty(tmp_path: Path) -> None:
    db_path = tmp_path / "state_fractional.db"
    store = SqliteStateStore(str(db_path))
    request = OrderRequest(
        symbol="BTCUSD",
        qty=0.998,
        side=OrderSide.SELL,
        client_order_id="cid-fractional",
    )
    store.save_intended_order("run-fractional", request)

    assert store.has_active_intent("BTCUSD", "sell", 0.998)
    assert not store.has_active_intent("BTCUSD", "sell", 1.0)
    store.close()

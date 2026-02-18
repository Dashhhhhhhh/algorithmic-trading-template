"""SQLite state store for restart-safe live trading."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from algotrade.domain.models import OrderRequest
from algotrade.state.store import OrderIntentRecord


class SqliteStateStore:
    """SQLite-backed implementation of runtime state persistence."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def record_run(
        self,
        run_id: str,
        mode: str,
        strategy_id: str,
        symbols: list[str],
    ) -> None:
        now = self._utc_now()
        symbols_text = ",".join(symbols)
        self.connection.execute(
            """
            INSERT OR REPLACE INTO runs(run_id, mode, strategy_id, symbols, started_ts)
            VALUES(?, ?, ?, ?, ?)
            """,
            (run_id, mode, strategy_id, symbols_text, now),
        )
        self.connection.commit()

    def save_intended_order(self, run_id: str, request: OrderRequest) -> None:
        if request.client_order_id is None:
            raise ValueError("request.client_order_id is required for persistence")
        now = self._utc_now()
        fingerprint = self._fingerprint(request.symbol, request.side.value, request.qty)
        self.connection.execute(
            """
            INSERT OR REPLACE INTO order_intents(
                client_order_id,
                run_id,
                symbol,
                side,
                qty,
                order_type,
                status,
                broker_order_id,
                fingerprint,
                created_ts,
                updated_ts
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.client_order_id,
                run_id,
                request.symbol,
                request.side.value,
                request.qty,
                request.order_type,
                "intended",
                None,
                fingerprint,
                now,
                now,
            ),
        )
        self.connection.commit()

    def mark_submitted(self, client_order_id: str, broker_order_id: str, status: str) -> None:
        now = self._utc_now()
        normalized_status = self._normalize_submission_status(status)
        self.connection.execute(
            """
            UPDATE order_intents
            SET broker_order_id = ?, status = ?, updated_ts = ?
            WHERE client_order_id = ?
            """,
            (broker_order_id, normalized_status, now, client_order_id),
        )
        self.connection.commit()

    def mark_reconciled(self, client_order_id: str, status: str) -> None:
        now = self._utc_now()
        self.connection.execute(
            """
            UPDATE order_intents
            SET status = ?, updated_ts = ?
            WHERE client_order_id = ?
            """,
            (status, now, client_order_id),
        )
        self.connection.commit()

    def list_active_intents(self) -> list[OrderIntentRecord]:
        rows = self.connection.execute(
            """
            SELECT
                client_order_id,
                run_id,
                symbol,
                side,
                qty,
                status,
                broker_order_id,
                fingerprint
            FROM order_intents
            WHERE status IN ('intended', 'submitted')
            ORDER BY created_ts ASC
            """
        ).fetchall()
        records: list[OrderIntentRecord] = []
        for row in rows:
            records.append(
                OrderIntentRecord(
                    client_order_id=str(row["client_order_id"]),
                    run_id=str(row["run_id"]),
                    symbol=str(row["symbol"]),
                    side=str(row["side"]),
                    qty=int(row["qty"]),
                    status=str(row["status"]),
                    broker_order_id=str(row["broker_order_id"]) if row["broker_order_id"] else None,
                    fingerprint=str(row["fingerprint"]),
                )
            )
        return records

    def has_active_intent(self, symbol: str, side: str, qty: int) -> bool:
        fingerprint = self._fingerprint(symbol, side, qty)
        row = self.connection.execute(
            """
            SELECT 1
            FROM order_intents
            WHERE fingerprint = ?
              AND status IN ('intended', 'submitted')
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self.connection.close()

    def _initialize_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs(
                run_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                symbols TEXT NOT NULL,
                started_ts TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_intents(
                client_order_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty INTEGER NOT NULL,
                order_type TEXT NOT NULL,
                status TEXT NOT NULL,
                broker_order_id TEXT,
                fingerprint TEXT NOT NULL,
                created_ts TEXT NOT NULL,
                updated_ts TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_order_intents_status
            ON order_intents(status)
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_order_intents_fingerprint
            ON order_intents(fingerprint)
            """
        )
        self.connection.commit()

    @staticmethod
    def _fingerprint(symbol: str, side: str, qty: int) -> str:
        return f"{symbol.upper()}|{side.lower()}|{int(qty)}"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(tz=UTC).isoformat()

    @staticmethod
    def _normalize_submission_status(status: str) -> str:
        terminal = {"filled", "canceled", "cancelled", "rejected"}
        normalized = status.strip().lower()
        if normalized in terminal:
            return normalized
        return "submitted"

"""State store contract used by runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from algotrade.domain.models import OrderRequest


@dataclass(frozen=True)
class OrderIntentRecord:
    """Persisted order intent for restart reconciliation."""

    client_order_id: str
    run_id: str
    symbol: str
    side: str
    qty: float
    status: str
    broker_order_id: str | None
    fingerprint: str


class StateStore(Protocol):
    """Persistence API for run and order-intent state."""

    def record_run(
        self,
        run_id: str,
        mode: str,
        strategy_id: str,
        symbols: list[str],
    ) -> None:
        """Persist run metadata."""

    def save_intended_order(
        self,
        run_id: str,
        request: OrderRequest,
    ) -> None:
        """Persist order intent before submission."""

    def mark_submitted(
        self,
        client_order_id: str,
        broker_order_id: str,
        status: str,
    ) -> None:
        """Persist broker submission status."""

    def mark_reconciled(
        self,
        client_order_id: str,
        status: str,
    ) -> None:
        """Mark intent as reconciled on restart."""

    def list_active_intents(self) -> list[OrderIntentRecord]:
        """Return unresolved intents."""

    def has_active_intent(self, symbol: str, side: str, qty: float) -> bool:
        """Return true when a matching unresolved intent exists."""

    def close(self) -> None:
        """Close persistence resources."""

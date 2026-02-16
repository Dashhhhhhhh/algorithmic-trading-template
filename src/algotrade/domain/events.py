"""Structured event stream models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .models import Mode


@dataclass(frozen=True)
class TradeEvent:
    """Single event written to JSONL."""

    run_id: str
    mode: Mode
    strategy_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())

    def to_record(self) -> dict[str, Any]:
        """Convert event to serializable dict."""
        return {
            "ts": self.ts,
            "run_id": self.run_id,
            "mode": self.mode,
            "strategy_id": self.strategy_id,
            "event_type": self.event_type,
            "payload": self.payload,
        }

"""Concise human-readable run logger."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any


class HumanLogger:
    """Console logger with fixed line types."""

    def __init__(self, level: str = "INFO") -> None:
        self._logger = logging.getLogger("algotrade")
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self._logger.propagate = False
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def run_started(
        self,
        run_id: str,
        mode: str,
        strategy_id: str,
        symbols: list[str],
    ) -> None:
        self._logger.info(
            "run_started | %s/%s | symbols=%s | run=%s",
            mode,
            strategy_id,
            ",".join(symbols),
            self._short_id(run_id),
        )

    def decision(
        self,
        symbol: str,
        target_qty: int,
        current_qty: int,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        delta = target_qty - current_qty
        summary = (
            f"decision | {symbol} | target {target_qty:+d} vs current {current_qty:+d} "
            f"(delta {delta:+d})"
        )
        parts = [summary]
        if details:
            parts.extend(self._decision_detail_parts(details))
        self._logger.info(" | ".join(parts))

    def order_submit(
        self,
        symbol: str,
        side: str,
        qty: int,
        client_order_id: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        parts = [
            f"submit | {symbol} {side.upper()} x{qty} | cid {self._short_id(client_order_id)}"
        ]
        if details:
            reference_price = self._as_float(details.get("reference_price"))
            est_notional = self._as_float(details.get("est_notional"))
            if reference_price is not None:
                parts.append(f"ref ${reference_price:,.3f}")
            if est_notional is not None:
                parts.append(f"est ${est_notional:,.2f}")
        self._logger.info(" | ".join(parts))

    def order_update(
        self,
        order_id: str,
        status: str,
        client_order_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        parts = [
            f"update | order {self._short_id(order_id)} | {self._human_status(status)}",
        ]
        if client_order_id:
            parts.append(f"cid {self._short_id(client_order_id)}")
        if details:
            filled_price = self._as_float(details.get("filled_avg_price"))
            filled_notional = self._as_float(details.get("filled_notional"))
            if filled_price is not None:
                parts.append(f"fill ${filled_price:,.3f}")
            if filled_notional is not None:
                parts.append(f"notional ${filled_notional:,.2f}")
            event_time = (
                details.get("filled_at")
                or details.get("updated_at")
                or details.get("submitted_at")
            )
            if isinstance(event_time, str) and event_time.strip():
                parts.append(f"at {self._short_ts(event_time)}")
        self._logger.info(" | ".join(parts))

    def cycle_summary(
        self,
        strategy_id: str,
        raw_orders: int,
        risk_orders: int,
        prepared_orders: int,
        risk_blocked: int,
        duplicate_blocked: int,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        parts = [
            f"cycle | {strategy_id}",
            f"orders {raw_orders}/{risk_orders}/{prepared_orders}",
            f"blocked r:{risk_blocked} d:{duplicate_blocked}",
        ]
        if details:
            equity = self._as_float(details.get("equity"))
            pnl_start = self._as_float(details.get("pnl_start"))
            pnl_prev = self._as_float(details.get("pnl_prev"))
            pnl_start_pct = self._as_float(details.get("pnl_start_pct"))

            if equity is not None:
                parts.append(f"equity ${equity:,.2f}")
            if pnl_start is not None:
                parts.append(f"run {pnl_start:+,.2f}")
            if pnl_start_pct is not None:
                parts.append(f"run% {pnl_start_pct * 100:+.3f}%")
            if pnl_prev is not None:
                parts.append(f"cycle {pnl_prev:+,.2f}")

        self._logger.info(" | ".join(parts))

    def error(self, message: str) -> None:
        self._logger.error("error | %s", message)

    @staticmethod
    def _short_id(value: str | None, head: int = 10, tail: int = 6) -> str:
        if not value:
            return ""
        text = str(value)
        if len(text) <= head + tail + 1:
            return text
        return f"{text[:head]}...{text[-tail:]}"

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _short_ts(value: str) -> str:
        text = value.strip()
        if not text:
            return text
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return text
        return parsed.strftime("%H:%M:%S")

    @staticmethod
    def _human_status(status: str) -> str:
        mapping = {
            "pending_new": "pending",
            "submitted": "submitted",
            "filled_reconciled": "filled",
            "stale_reconciled": "stale",
            "duplicate_blocked": "blocked: duplicate",
        }
        return mapping.get(status, status)

    def _decision_detail_parts(self, details: Mapping[str, Any]) -> list[str]:
        parts: list[str] = []
        bar_time = details.get("asof")
        if isinstance(bar_time, str) and bar_time.strip():
            parts.append(f"bar {self._short_ts(bar_time)}")

        close = self._as_float(details.get("close"))
        if close is not None:
            parts.append(f"close ${close:,.3f}")

        ret_1 = self._as_float(details.get("ret_1"))
        if ret_1 is not None:
            parts.append(f"ret1 {ret_1 * 100:+.3f}%")

        ret_lb = self._as_float(details.get("ret_lb"))
        if ret_lb is not None:
            parts.append(f"retLB {ret_lb * 100:+.3f}%")

        volume = self._as_float(details.get("volume"))
        if volume is not None:
            parts.append(f"vol {int(volume):,}")

        return parts

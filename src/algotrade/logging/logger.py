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
        _ = (run_id, mode, strategy_id, symbols)
        return None

    def decision(
        self,
        symbol: str,
        target_qty: float,
        current_qty: float,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        _ = (symbol, target_qty, current_qty, details)
        return None

    def order_submit(
        self,
        symbol: str,
        side: str,
        qty: float,
        client_order_id: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        _ = client_order_id
        normalized_side = side.strip().lower()
        buy_amount = qty if normalized_side == "buy" else 0.0
        sell_amount = qty if normalized_side == "sell" else 0.0
        buy_amount_text = self._format_qty(buy_amount)
        sell_amount_text = self._format_qty(sell_amount)
        reference_price: float | None = None
        if details:
            reference_price = self._as_float(details.get("reference_price"))
        if reference_price is not None:
            buy_amount_text = f"{buy_amount_text} (${buy_amount * reference_price:,.2f})"
            sell_amount_text = f"{sell_amount_text} (${sell_amount * reference_price:,.2f})"
        parts = [
            f"submit | {symbol} | buy_amount {buy_amount_text} "
            f"| sell_amount {sell_amount_text}"
        ]
        if reference_price is not None:
            parts.append(f"ref ${reference_price:,.3f}")
        self._logger.info(" | ".join(parts))

    def order_update(
        self,
        order_id: str,
        status: str,
        client_order_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        _ = client_order_id
        if str(order_id).lower() in {"risk", "dedupe", "reconcile", "portfolio"}:
            return None
        if str(status).lower() in {"stale_reconciled", "duplicate_blocked"}:
            return None
        parts = [f"update | {self._human_status(status)}"]
        if details:
            filled_price = self._as_float(details.get("filled_avg_price"))
            filled_notional = self._as_float(details.get("filled_notional"))
            if filled_price is not None:
                parts.append(f"fill ${filled_price:,.3f}")
            if filled_notional is not None:
                parts.append(f"fill_usd ${filled_notional:,.2f}")
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
        _ = (
            strategy_id,
            raw_orders,
            risk_orders,
            prepared_orders,
            risk_blocked,
            duplicate_blocked,
            details,
        )
        return None

    def portfolio(self, cash: float, equity: float, buying_power: float) -> None:
        self._logger.info(
            "portfolio | cash $%s | equity $%s | buying_power $%s",
            f"{cash:,.2f}",
            f"{equity:,.2f}",
            f"{buying_power:,.2f}",
        )

    def position(self, symbol: str, qty: float) -> None:
        self._logger.info("position | %s | qty %s", symbol, self._format_qty(qty, signed=True))

    def cash(self, cash: float) -> None:
        self._logger.info("cash | $%s", f"{cash:,.2f}")

    def position_exposure(
        self,
        symbol: str,
        qty: float,
        market_value: float | None = None,
        cost_basis: float | None = None,
        unrealized_pl: float | None = None,
    ) -> None:
        qty_text = f"{qty:+.8f}".rstrip("0").rstrip(".")
        if qty_text in {"+", "-"}:
            qty_text = f"{qty:+.0f}"
        parts = [f"position | {symbol} | qty {qty_text}"]
        if market_value is not None:
            parts.append(f"value ${market_value:,.2f}")
        if cost_basis is not None:
            parts.append(f"cost ${cost_basis:,.2f}")
        if unrealized_pl is not None:
            parts.append(f"upl {unrealized_pl:+,.2f}")
        self._logger.info(" | ".join(parts))

    def error(self, message: str) -> None:
        self._logger.error("error | %s", message)

    def run_pnl(
        self,
        equity: float,
        pnl: float,
        pnl_pct: float,
        start_equity: float | None = None,
    ) -> None:
        if start_equity is None:
            start_equity = equity - pnl
        self._logger.info(
            "pnl | session_start_equity $%s | session_end_equity $%s "
            "| session_pnl %s | session_pnl%% %s",
            f"{start_equity:,.2f}",
            f"{equity:,.2f}",
            f"{pnl:+,.2f}",
            f"{pnl_pct * 100.0:+,.3f}%",
        )

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
    def _format_qty(value: float, signed: bool = False, precision: int = 8) -> str:
        normalized = 0.0 if abs(float(value)) < 1e-9 else float(value)
        template = f"{{:{'+' if signed else ''}.{max(0, precision)}f}}"
        text = template.format(normalized).rstrip("0").rstrip(".")
        if text in {"", "+", "-"}:
            return "+0" if signed else "0"
        if text == "-0":
            return "+0" if signed else "0"
        return text

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
            "closed_reconciled": "closed",
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

        return parts

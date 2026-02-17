"""Concise human-readable run logger."""

from __future__ import annotations

import logging
from collections.abc import Mapping
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
            "run_started run_id=%s mode=%s strategy=%s symbols=%s",
            run_id,
            mode,
            strategy_id,
            ",".join(symbols),
        )

    def decision(
        self,
        symbol: str,
        target_qty: int,
        current_qty: int,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if details:
            fields = " ".join(f"{key}={details[key]}" for key in sorted(details))
            self._logger.info(
                "decision symbol=%s target=%s current=%s %s",
                symbol,
                target_qty,
                current_qty,
                fields,
            )
            return
        self._logger.info(
            "decision symbol=%s target=%s current=%s",
            symbol,
            target_qty,
            current_qty,
        )

    def order_submit(self, symbol: str, side: str, qty: int, client_order_id: str) -> None:
        self._logger.info(
            "order_submit symbol=%s side=%s qty=%s client_order_id=%s",
            symbol,
            side,
            qty,
            client_order_id,
        )

    def order_update(self, order_id: str, status: str, client_order_id: str | None = None) -> None:
        self._logger.info(
            "order_update order_id=%s status=%s client_order_id=%s",
            order_id,
            status,
            client_order_id or "",
        )

    def error(self, message: str) -> None:
        self._logger.error("error message=%s", message)

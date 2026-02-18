"""Alpaca broker adapter for live mode (paper or live endpoint)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import sleep
from typing import Any

import requests

from algotrade.domain.models import (
    Order,
    OrderReceipt,
    OrderRequest,
    OrderSide,
    PortfolioSnapshot,
    Position,
)


class AlpacaPaperBroker:
    """REST broker wrapper with retry and rate-limit handling."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str,
        timeout: int = 20,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "Content-Type": "application/json",
            }
        )

    def get_portfolio(self) -> PortfolioSnapshot:
        payload = self._request("GET", "/v2/account")
        equity = float(
            payload.get("equity", payload.get("portfolio_value", payload.get("cash", 0)))
        )
        cash = float(payload.get("cash", 0))
        buying_power = float(payload.get("buying_power", cash))
        positions = self.get_positions()
        return PortfolioSnapshot(
            cash=cash,
            equity=equity,
            buying_power=buying_power,
            positions=positions,
        )

    def get_positions(self) -> dict[str, Position]:
        payload = self._request("GET", "/v2/positions")
        positions: dict[str, Position] = {}
        for item in payload if isinstance(payload, list) else []:
            symbol = str(item.get("symbol", "")).upper()
            side = str(item.get("side", "long")).lower()
            raw_qty = abs(self._parse_optional_float(item.get("qty")) or 0.0)
            signed_qty = -raw_qty if side == "short" else raw_qty
            positions[symbol] = Position(symbol=symbol, qty=signed_qty)
        return positions

    def get_positions_details(self) -> list[dict[str, Any]]:
        """Return position-level quantity and cash-value diagnostics."""
        payload = self._request("GET", "/v2/positions")
        details: list[dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else []:
            symbol = str(item.get("symbol", "")).upper()
            side = str(item.get("side", "long")).lower()
            raw_qty = self._parse_optional_float(item.get("qty"))
            qty = raw_qty if raw_qty is not None else None
            if qty is not None and side == "short":
                qty = -abs(qty)
            details.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "market_value": self._parse_optional_float(item.get("market_value")),
                    "cost_basis": self._parse_optional_float(item.get("cost_basis")),
                    "unrealized_pl": self._parse_optional_float(item.get("unrealized_pl")),
                }
            )
        return details

    def get_open_orders(self) -> list[Order]:
        payload = self._request(
            "GET",
            "/v2/orders",
            params={"status": "open", "direction": "desc", "limit": "100"},
        )
        orders: list[Order] = []
        for item in payload if isinstance(payload, list) else []:
            side = self._to_order_side(str(item.get("side", "buy")))
            orders.append(
                Order(
                    order_id=str(item.get("id", "")),
                    symbol=str(item.get("symbol", "")).upper(),
                    side=side,
                    qty=self._parse_optional_float(item.get("qty")) or 0.0,
                    status=str(item.get("status", "")),
                    client_order_id=str(item.get("client_order_id", "")) or None,
                )
            )
        return orders

    def submit_orders(self, requests_to_submit: list[OrderRequest]) -> list[OrderReceipt]:
        receipts: list[OrderReceipt] = []
        for request in requests_to_submit:
            body: dict[str, Any] = {
                "symbol": self.normalize_symbol(request.symbol),
                "qty": request.qty,
                "side": request.side.value,
                "type": request.order_type,
                "time_in_force": self._resolve_time_in_force(request),
            }
            if request.client_order_id:
                body["client_order_id"] = request.client_order_id
            payload = self._request("POST", "/v2/orders", json=body)
            receipt = OrderReceipt(
                order_id=str(payload.get("id", "")),
                symbol=str(payload.get("symbol", request.symbol)).upper(),
                side=self._to_order_side(str(payload.get("side", request.side.value))),
                qty=float(payload.get("qty", request.qty)),
                status=str(payload.get("status", "submitted")),
                client_order_id=(
                    str(payload.get("client_order_id", request.client_order_id or ""))
                    or request.client_order_id
                ),
                raw=payload if isinstance(payload, dict) else {},
            )
            receipts.append(receipt)
        return receipts

    def close_all_positions(self, cancel_orders: bool = True) -> list[dict[str, Any]]:
        """Close every open position using Alpaca's server-side liquidation endpoint."""
        params = {"cancel_orders": "true"} if cancel_orders else None
        payload = self._request("DELETE", "/v2/positions", params=params)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    def subscribe_trade_updates(self, handler: Callable[[Order], None]) -> None:
        _ = handler
        raise NotImplementedError("Websocket trade updates are not implemented in this boilerplate")

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                sleep(float(attempt))
                continue

            if response.status_code == 429:
                if attempt == self.max_retries:
                    detail = response.text.strip() or "Rate limit"
                    raise ValueError(f"Alpaca API error 429 for {path}: {detail}")
                sleep(self._retry_after_seconds(response.headers, attempt))
                continue

            if response.status_code >= 500:
                if attempt == self.max_retries:
                    detail = response.text.strip() or "Server error"
                    raise ValueError(
                        f"Alpaca API error {response.status_code} for {path}: {detail}"
                    )
                sleep(float(attempt))
                continue

            if response.status_code >= 400:
                detail = response.text.strip() or "Request rejected"
                raise ValueError(f"Alpaca API error {response.status_code} for {path}: {detail}")

            try:
                return response.json()
            except ValueError as exc:
                raise ValueError(f"Alpaca response for {path} was not valid JSON") from exc

        if last_error is not None:
            raise ValueError(f"Alpaca request failed for {path}: {last_error}") from last_error
        raise ValueError(f"Alpaca request failed for {path}")

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper().replace("/", "").replace("-", "")
        if normalized.endswith("USDT") and len(normalized) >= 7:
            return f"{normalized[:-4]}USD"
        return normalized

    @staticmethod
    def _is_crypto_symbol(symbol: str) -> bool:
        normalized = AlpacaPaperBroker.normalize_symbol(symbol)
        return normalized.endswith("USD") and len(normalized) >= 6

    @staticmethod
    def _to_order_side(value: str) -> OrderSide:
        normalized = value.strip().lower()
        if normalized == "sell":
            return OrderSide.SELL
        return OrderSide.BUY

    def _resolve_time_in_force(self, request: OrderRequest) -> str:
        if request.time_in_force:
            requested = request.time_in_force
        else:
            requested = "day"
        if self._is_crypto_symbol(request.symbol) and requested.lower() == "day":
            return "gtc"
        return requested

    @staticmethod
    def _retry_after_seconds(
        headers: requests.structures.CaseInsensitiveDict,
        attempt: int,
    ) -> float:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                try:
                    dt = parsedate_to_datetime(retry_after)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    delta = (dt - datetime.now(tz=UTC)).total_seconds()
                    return max(delta, 1.0)
                except Exception:
                    pass

        rate_reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
        if rate_reset:
            try:
                reset_seconds = float(rate_reset)
                now_seconds = datetime.now(tz=UTC).timestamp()
                delta = reset_seconds - now_seconds
                return max(delta, 1.0)
            except ValueError:
                pass

        return max(float(attempt), 1.0)

    @staticmethod
    def _parse_optional_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text or text.lower() in {"none", "null"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None

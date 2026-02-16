"""Minimal Alpaca trading client (paper/live via base URL)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.broker.models import AccountInfo, MarketClock, OrderRequest, Position
from app.utils.errors import BrokerError


class AlpacaClient:
    """Small wrapper around Alpaca REST endpoints used by this project."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str = "https://paper-api.alpaca.markets",
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = logging.getLogger("algotrade.broker.alpaca")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "Content-Type": "application/json",
            }
        )

    def get_account(self) -> AccountInfo:
        """Return current account info."""
        payload = self._request("GET", "/v2/account")
        equity = float(payload.get("equity", payload.get("portfolio_value", payload["cash"])))
        last_equity = float(
            payload.get(
                "last_equity",
                payload.get("last_portfolio_value", payload["cash"]),
            )
        )
        return AccountInfo(
            id=str(payload["id"]),
            status=str(payload["status"]),
            cash=float(payload["cash"]),
            buying_power=float(payload["buying_power"]),
            trading_blocked=bool(payload["trading_blocked"]),
            equity=equity,
            last_equity=last_equity,
        )

    def get_positions(self) -> dict[str, Position]:
        """Return open positions keyed by symbol."""
        payload = self._request("GET", "/v2/positions")
        positions: dict[str, Position] = {}
        for item in payload:
            symbol = str(item["symbol"]).upper()
            positions[symbol] = Position(
                symbol=symbol,
                qty=float(item["qty"]),
                side=str(item.get("side", "")),
            )
        return positions

    def submit_market_order(self, request: OrderRequest) -> dict[str, Any]:
        """Submit a market order and return raw JSON response."""
        normalized_symbol = self.normalize_symbol(request.symbol)
        time_in_force = request.time_in_force
        if self._is_crypto_symbol(normalized_symbol) and time_in_force == "day":
            # Alpaca crypto market orders reject DAY; use GTC by default.
            time_in_force = "gtc"
        body = {
            "symbol": normalized_symbol,
            "qty": request.qty,
            "side": request.side.value,
            "type": request.type,
            "time_in_force": time_in_force,
        }
        return self._request("POST", "/v2/orders", json=body)

    def get_order(self, order_id: str) -> dict[str, Any]:
        """Get one order by id."""
        return self._request("GET", f"/v2/orders/{order_id}")

    def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Return currently open orders, optionally filtered by symbol."""
        params: dict[str, str] = {"status": "open", "direction": "desc", "limit": "50"}
        if symbol:
            params["symbols"] = self.normalize_symbol(symbol)
        payload = self._request("GET", "/v2/orders", params=params)
        return payload if isinstance(payload, list) else []

    def get_clock(self) -> MarketClock:
        """Return market open/close state."""
        payload = self._request("GET", "/v2/clock")
        return MarketClock(
            is_open=bool(payload.get("is_open", False)),
            timestamp=str(payload.get("timestamp", "")),
            next_open=str(payload.get("next_open", "")),
            next_close=str(payload.get("next_close", "")),
        )

    def cancel_order(self, order_id: str) -> None:
        """Cancel one order by id."""
        path = f"/v2/orders/{order_id}"
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method="DELETE",
                url=url,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BrokerError(f"Alpaca cancel request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or "No response body."
            raise BrokerError(
                f"Alpaca API error {response.status_code} for {path}: {detail}"
            )

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=json,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BrokerError(f"Alpaca request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip() or "No response body."
            raise BrokerError(
                f"Alpaca API error {response.status_code} for {path}: {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise BrokerError(f"Invalid JSON response from Alpaca for {path}.") from exc

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """Normalize user symbols to Alpaca trading symbol format.

        Examples:
        - BTCUSDT -> BTCUSD
        - BTC/USDT -> BTCUSD
        - BTC/USD -> BTCUSD
        """
        normalized = symbol.strip().upper().replace("/", "").replace("-", "")
        if normalized.endswith("USDT") and len(normalized) >= 7:
            return f"{normalized[:-4]}USD"
        return normalized

    @staticmethod
    def _is_crypto_symbol(symbol: str) -> bool:
        normalized = AlpacaClient.normalize_symbol(symbol)
        return normalized.endswith("USD") and len(normalized) >= 6

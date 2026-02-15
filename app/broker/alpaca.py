"""Minimal Alpaca trading client (paper/live via base URL)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.broker.models import AccountInfo, OrderRequest, Position
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
        return AccountInfo(
            id=str(payload["id"]),
            status=str(payload["status"]),
            cash=float(payload["cash"]),
            buying_power=float(payload["buying_power"]),
            trading_blocked=bool(payload["trading_blocked"]),
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
        body = {
            "symbol": request.symbol.upper(),
            "qty": request.qty,
            "side": request.side.value,
            "type": request.type,
            "time_in_force": request.time_in_force,
        }
        return self._request("POST", "/v2/orders", json=body)

    def _request(self, method: str, path: str, json: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=json,
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


"""Tests for broker/data symbol normalization helpers."""

from __future__ import annotations

from app.broker.alpaca import AlpacaClient
from app.broker.models import OrderRequest, OrderSide
from app.data.alpaca_data import AlpacaDataClient


def test_broker_normalize_symbol_for_crypto_aliases() -> None:
    assert AlpacaClient.normalize_symbol("BTCUSDT") == "BTCUSD"
    assert AlpacaClient.normalize_symbol("btc/usdt") == "BTCUSD"
    assert AlpacaClient.normalize_symbol("BTC/USD") == "BTCUSD"
    assert AlpacaClient.normalize_symbol("SPY") == "SPY"


def test_data_client_crypto_symbol_detection() -> None:
    assert AlpacaDataClient._is_crypto_symbol("BTCUSDT")
    assert AlpacaDataClient._is_crypto_symbol("BTCUSD")
    assert AlpacaDataClient._is_crypto_symbol("BTC/USD")
    assert not AlpacaDataClient._is_crypto_symbol("SPY")


def test_data_client_alpaca_crypto_symbol_format() -> None:
    assert AlpacaDataClient._to_alpaca_crypto_symbol("BTCUSDT") == "BTC/USD"
    assert AlpacaDataClient._to_alpaca_crypto_symbol("btc/usdt") == "BTC/USD"
    assert AlpacaDataClient._to_alpaca_crypto_symbol("ETHUSD") == "ETH/USD"


class _CaptureAlpacaClient(AlpacaClient):
    def __init__(self) -> None:
        super().__init__(api_key="x", secret_key="y")
        self.last_request: dict | None = None

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> dict:
        self.last_request = {
            "method": method,
            "path": path,
            "json": json,
            "params": params,
        }
        return {}


def test_submit_market_order_sets_gtc_for_crypto() -> None:
    client = _CaptureAlpacaClient()
    client.submit_market_order(
        OrderRequest(symbol="BTCUSDT", qty=1, side=OrderSide.BUY),
    )
    assert client.last_request is not None
    assert client.last_request["json"]["symbol"] == "BTCUSD"
    assert client.last_request["json"]["time_in_force"] == "gtc"


def test_submit_market_order_keeps_day_for_equity() -> None:
    client = _CaptureAlpacaClient()
    client.submit_market_order(
        OrderRequest(symbol="SPY", qty=1, side=OrderSide.BUY),
    )
    assert client.last_request is not None
    assert client.last_request["json"]["symbol"] == "SPY"
    assert client.last_request["json"]["time_in_force"] == "day"

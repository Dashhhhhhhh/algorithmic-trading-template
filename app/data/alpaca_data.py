"""Alpaca market data client for fetching historical/live bars."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from app.utils.errors import DataProviderError


class AlpacaDataClient:
    """Fetch OHLCV bars from Alpaca Data API.

    Uses endpoint:
    GET /v2/stocks/{symbol}/bars
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        data_base_url: str = "https://data.alpaca.markets",
        timeframe: str = "1Day",
        limit: int = 200,
        lookback_days: int = 365,
        timeout: int = 15,
        max_retries: int = 3,
    ) -> None:
        self.data_base_url = data_base_url.rstrip("/")
        self.timeframe = timeframe
        self.limit = limit
        self.lookback_days = lookback_days
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger("algotrade.data.alpaca")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            }
        )

    def fetch_daily(self, symbol: str, adjusted: bool = False) -> pd.DataFrame:
        _ = adjusted
        symbol = symbol.upper()
        timeframe = self._normalize_timeframe(self.timeframe)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=self.lookback_days)
        if self._is_crypto_symbol(symbol):
            bars = self._fetch_crypto_bars(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
        else:
            bars = self._fetch_stock_bars(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
        if not bars:
            raise DataProviderError(f"Alpaca data returned no bars for {symbol}.")

        frame = self._bars_to_frame(symbol=symbol, bars=bars)
        if frame.empty:
            raise DataProviderError(f"Alpaca bars for {symbol} were empty after parsing.")
        return frame

    def _fetch_stock_bars(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        path = f"/v2/stocks/{symbol}/bars"
        params = {
            "timeframe": timeframe,
            "limit": str(self.limit),
            "adjustment": "raw",
            "feed": "iex",
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "sort": "asc",
        }
        payload = self._request_with_retry(path=path, params=params)
        bars = payload.get("bars", [])
        return bars if isinstance(bars, list) else []

    def _fetch_crypto_bars(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        pair = self._to_alpaca_crypto_symbol(symbol)
        path = "/v1beta3/crypto/us/bars"
        params = {
            "symbols": pair,
            "timeframe": timeframe,
            "limit": str(self.limit),
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "sort": "asc",
        }
        payload = self._request_with_retry(path=path, params=params)
        raw_bars = payload.get("bars", {})

        if isinstance(raw_bars, dict):
            bars = raw_bars.get(pair)
            if bars is None:
                bars = raw_bars.get(pair.replace("/", ""))
            if bars is None and len(raw_bars) == 1:
                bars = next(iter(raw_bars.values()))
            return bars if isinstance(bars, list) else []

        if isinstance(raw_bars, list):
            return raw_bars

        return []

    @staticmethod
    def _bars_to_frame(symbol: str, bars: list[dict]) -> pd.DataFrame:
        frame = pd.DataFrame(bars)
        required = {"o", "h", "l", "c", "v", "t"}
        if not required.issubset(frame.columns):
            raise DataProviderError(f"Alpaca data payload missing required fields for {symbol}.")

        frame = frame.rename(
            columns={
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
                "t": "time",
            }
        )
        frame.index = pd.to_datetime(frame["time"], utc=False)
        frame = frame.sort_index()
        frame = frame[["open", "high", "low", "close", "volume"]]
        return frame.apply(pd.to_numeric, errors="coerce").dropna()

    @staticmethod
    def _is_crypto_symbol(symbol: str) -> bool:
        compact = symbol.strip().upper().replace("/", "").replace("-", "")
        if compact.endswith("USDT") and len(compact) >= 7:
            return True
        if compact.endswith("USD") and len(compact) >= 6:
            return True
        return False

    @staticmethod
    def _to_alpaca_crypto_symbol(symbol: str) -> str:
        compact = symbol.strip().upper().replace("/", "").replace("-", "")
        if compact.endswith("USDT"):
            compact = f"{compact[:-4]}USD"
        if not compact.endswith("USD") or len(compact) <= 3:
            return symbol.strip().upper()
        base = compact[:-3]
        return f"{base}/USD"

    def _request_with_retry(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.data_base_url}{path}"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 429:
                    raise DataProviderError("Alpaca data rate limit hit.")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, DataProviderError) as exc:
                if attempt == self.max_retries:
                    raise DataProviderError(f"Failed Alpaca data request: {exc}") from exc
                sleep_seconds = attempt * 2
                self.logger.warning(
                    "Alpaca data request failed (attempt %s/%s). Retrying in %ss.",
                    attempt,
                    self.max_retries,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        raise DataProviderError("Alpaca data request retries exhausted.")

    @staticmethod
    def _normalize_timeframe(value: str) -> str:
        """Map common timeframe aliases to Alpaca format."""
        normalized = value.strip().lower()
        mapping = {
            "1d": "1Day",
            "day": "1Day",
            "1day": "1Day",
            "1min": "1Min",
            "1m": "1Min",
            "5min": "5Min",
            "15min": "15Min",
            "1h": "1Hour",
            "1hour": "1Hour",
        }
        return mapping.get(normalized, value)

"""Alpaca market data provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import sleep

import pandas as pd
import requests


class AlpacaMarketDataProvider:
    """Fetch OHLCV bars from Alpaca's data API."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        data_base_url: str,
        timeframe: str,
        lookback_days: int = 365,
        limit: int = 500,
        timeout: int = 20,
        max_retries: int = 3,
    ) -> None:
        self.data_base_url = data_base_url.rstrip("/")
        self.timeframe = self._normalize_timeframe(timeframe)
        self.lookback_days = lookback_days
        self.limit = limit
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            }
        )

    def get_bars(self, symbol: str) -> pd.DataFrame:
        normalized_symbol = symbol.strip().upper()
        end_time = datetime.now(tz=UTC)
        start_time = end_time - timedelta(days=self.lookback_days)
        if self._is_crypto_symbol(normalized_symbol):
            bars = self._fetch_crypto_bars(normalized_symbol, start_time, end_time)
        else:
            bars = self._fetch_stock_bars(normalized_symbol, start_time, end_time)
        frame = self._bars_to_frame(normalized_symbol, bars)
        if frame.empty:
            raise ValueError(f"No bars returned for {symbol}")
        return frame

    def _fetch_stock_bars(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        payload = self._request_with_retry(
            path=f"/v2/stocks/{symbol}/bars",
            params={
                "timeframe": self.timeframe,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "limit": str(self.limit),
                "adjustment": "raw",
                "feed": "iex",
                "sort": "asc",
            },
        )
        bars = payload.get("bars", [])
        return bars if isinstance(bars, list) else []

    def _fetch_crypto_bars(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        alpaca_symbol = self._to_alpaca_crypto_symbol(symbol)
        payload = self._request_with_retry(
            path="/v1beta3/crypto/us/bars",
            params={
                "symbols": alpaca_symbol,
                "timeframe": self.timeframe,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "limit": str(self.limit),
                "sort": "asc",
            },
        )
        raw = payload.get("bars", {})
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            bars = raw.get(alpaca_symbol)
            if bars is None:
                bars = raw.get(alpaca_symbol.replace("/", ""))
            if bars is None and len(raw) == 1:
                bars = next(iter(raw.values()))
            return bars if isinstance(bars, list) else []
        return []

    def _request_with_retry(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.data_base_url}{path}"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ValueError(f"Alpaca data request failed: {exc}") from exc
                sleep(float(attempt))
                continue
            if response.status_code == 429:
                if attempt == self.max_retries:
                    raise ValueError("Alpaca data rate limit exceeded")
                sleep(float(attempt))
                continue
            if response.status_code >= 500:
                if attempt == self.max_retries:
                    raise ValueError(f"Alpaca data server error: {response.status_code}")
                sleep(float(attempt))
                continue
            if response.status_code >= 400:
                detail = response.text.strip() or "No response body"
                raise ValueError(f"Alpaca data error {response.status_code}: {detail}")
            return response.json()
        raise ValueError("Alpaca data request exhausted retries")

    @staticmethod
    def _bars_to_frame(symbol: str, bars: list[dict]) -> pd.DataFrame:
        frame = pd.DataFrame(bars)
        required = {"o", "h", "l", "c", "v", "t"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{symbol}: bar payload missing OHLCV fields")
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
        frame.index = pd.to_datetime(frame["time"], utc=True)
        frame = frame.sort_index()
        frame = frame[["open", "high", "low", "close", "volume"]]
        return frame.apply(pd.to_numeric, errors="coerce").dropna()

    @staticmethod
    def _normalize_timeframe(value: str) -> str:
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
        normalized = value.strip().lower()
        return mapping.get(normalized, value)

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
        if compact.endswith("USD") and len(compact) > 3:
            return f"{compact[:-3]}/USD"
        return symbol.strip().upper()

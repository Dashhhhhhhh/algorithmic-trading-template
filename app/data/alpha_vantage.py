"""Alpha Vantage HTTP client for historical daily OHLCV data."""

from __future__ import annotations

import logging
import time

import pandas as pd
import requests

from app.utils.errors import DataProviderError


class AlphaVantageClient:
    """Minimal Alpha Vantage client with basic retry/rate-limit handling."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, timeout: int = 15, max_retries: int = 3) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger("algotrade.data.alpha_vantage")

    def fetch_daily(self, symbol: str, adjusted: bool = False) -> pd.DataFrame:
        """Fetch daily bars and return a normalized OHLCV DataFrame.

        Returns:
            DataFrame with datetime index and columns:
            open, high, low, close, volume
        """
        function = "TIME_SERIES_DAILY_ADJUSTED" if adjusted else "TIME_SERIES_DAILY"
        params = {
            "function": function,
            "symbol": symbol.upper(),
            "outputsize": "compact",
            "apikey": self.api_key,
        }

        payload = self._request_with_retry(params=params)
        time_series_key = (
            "Time Series (Daily)"
            if "Time Series (Daily)" in payload
            else "Time Series (Daily Adjusted)"
        )

        if time_series_key not in payload:
            raise DataProviderError(
                f"Alpha Vantage response missing daily time series for symbol {symbol}."
            )

        series = payload[time_series_key]
        frame = pd.DataFrame.from_dict(series, orient="index")
        frame.index = pd.to_datetime(frame.index, utc=False)
        frame = frame.sort_index()

        # Adjusted and non-adjusted daily endpoints use slightly different names.
        volume_col = "6. volume" if "6. volume" in frame.columns else "5. volume"
        rename_map = {
            "1. open": "open",
            "2. high": "high",
            "3. low": "low",
            "4. close": "close",
            volume_col: "volume",
        }

        frame = frame.rename(columns=rename_map)
        required_cols = ["open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in frame.columns]
        if missing_cols:
            raise DataProviderError(
                f"Data for {symbol} missing required columns: {missing_cols}"
            )

        frame = frame[required_cols].apply(pd.to_numeric, errors="coerce").dropna()
        return frame

    def _request_with_retry(self, params: dict[str, str]) -> dict:
        """Perform GET request with simple backoff on rate-limit/transient failures."""
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(self.BASE_URL, params=params, timeout=self.timeout)
                response.raise_for_status()
                payload: dict = response.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise DataProviderError(
                        f"Failed to fetch data from Alpha Vantage: {exc}"
                    ) from exc
                sleep_seconds = attempt * 2
                self.logger.warning(
                    "Alpha Vantage request failed (attempt %s/%s). Retrying in %ss.",
                    attempt,
                    self.max_retries,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)
                continue

            if "Note" in payload:
                # Free tier rate-limit reached. Back off and retry.
                if attempt == self.max_retries:
                    raise DataProviderError(
                        "Alpha Vantage rate limit reached. Try again in a minute."
                    )
                sleep_seconds = attempt * 15
                self.logger.warning(
                    "Alpha Vantage rate limit hit (attempt %s/%s). Waiting %ss.",
                    attempt,
                    self.max_retries,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)
                continue

            if "Error Message" in payload:
                raise DataProviderError(
                    f"Alpha Vantage returned an error: {payload['Error Message']}"
                )

            return payload

        raise DataProviderError("Exhausted retries for Alpha Vantage request.")


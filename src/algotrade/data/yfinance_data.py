"""Yahoo Finance market data provider."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


class YFinanceDataProvider:
    """Fetch OHLCV bars from Yahoo Finance via yfinance."""

    def __init__(self, timeframe: str) -> None:
        self.interval = self._normalize_interval(timeframe)
        self.period = self._period_for_interval(self.interval)

    def get_bars(self, symbol: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ValueError(
                "yfinance is required for missing-data fallback. Install it with `uv add yfinance`."
            ) from exc

        ticker = self._resolve_yfinance_symbol(symbol)
        try:
            history = yf.Ticker(ticker).history(
                period=self.period,
                interval=self.interval,
                auto_adjust=False,
                actions=False,
            )
        except Exception as exc:
            raise ValueError(f"yfinance request failed for {symbol} ({ticker}): {exc}") from exc

        frame = self._normalize_history(history, symbol, ticker)
        if frame.empty:
            raise ValueError(f"yfinance returned no rows for {symbol} ({ticker})")
        return frame

    @staticmethod
    def _normalize_history(history: Any, symbol: str, ticker: str) -> pd.DataFrame:
        if history is None:
            raise ValueError(f"yfinance returned no rows for {symbol} ({ticker})")
        frame = pd.DataFrame(history).copy()
        if frame.empty:
            raise ValueError(f"yfinance returned no rows for {symbol} ({ticker})")

        open_column = YFinanceDataProvider._pick_column(frame, "open")
        high_column = YFinanceDataProvider._pick_column(frame, "high")
        low_column = YFinanceDataProvider._pick_column(frame, "low")
        close_column = YFinanceDataProvider._pick_column(frame, "close")
        if close_column is None:
            close_column = YFinanceDataProvider._pick_column(frame, "adj_close")
        volume_column = YFinanceDataProvider._pick_column(frame, "volume")

        if open_column is None or high_column is None or low_column is None or close_column is None:
            raise ValueError(f"yfinance payload missing OHLC columns for {symbol} ({ticker})")

        normalized = pd.DataFrame(index=pd.to_datetime(frame.index, utc=False))
        normalized["open"] = pd.to_numeric(frame[open_column], errors="coerce")
        normalized["high"] = pd.to_numeric(frame[high_column], errors="coerce")
        normalized["low"] = pd.to_numeric(frame[low_column], errors="coerce")
        normalized["close"] = pd.to_numeric(frame[close_column], errors="coerce")
        if volume_column is None:
            normalized["volume"] = 0.0
        else:
            normalized["volume"] = pd.to_numeric(frame[volume_column], errors="coerce").fillna(0.0)
        normalized = normalized.sort_index()
        normalized = normalized.dropna(subset=["open", "high", "low", "close"])
        return normalized

    @staticmethod
    def _pick_column(frame: pd.DataFrame, field: str) -> Any | None:
        for column in frame.columns:
            key = YFinanceDataProvider._column_key(column)
            if key == field or key.startswith(f"{field}_"):
                return column
        return None

    @staticmethod
    def _column_key(value: Any) -> str:
        if isinstance(value, tuple):
            text = "_".join(str(part) for part in value if part is not None)
        else:
            text = str(value)
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
        return normalized

    @staticmethod
    def _normalize_interval(value: str) -> str:
        mapping = {
            "1d": "1d",
            "day": "1d",
            "1day": "1d",
            "1min": "1m",
            "1m": "1m",
            "5min": "5m",
            "5m": "5m",
            "15min": "15m",
            "15m": "15m",
            "1h": "60m",
            "1hour": "60m",
            "60m": "60m",
        }
        normalized = value.strip().lower()
        return mapping.get(normalized, "1d")

    @staticmethod
    def _period_for_interval(interval: str) -> str:
        if interval == "1m":
            return "7d"
        intraday_intervals = {"2m", "5m", "15m", "30m", "60m", "90m"}
        if interval in intraday_intervals:
            return "60d"
        return "max"

    @staticmethod
    def _resolve_yfinance_symbol(symbol: str) -> str:
        market, bare_symbol = YFinanceDataProvider._split_market_symbol(symbol)
        compact = bare_symbol.strip().upper().replace("/", "").replace("-", "")

        if market == "CRYPTO" or YFinanceDataProvider._looks_like_crypto_symbol(compact):
            for quote in ("USDT", "USD"):
                if compact.endswith(quote) and len(compact) > len(quote):
                    base = compact[: -len(quote)]
                    normalized_quote = "USD" if quote == "USDT" else quote
                    return f"{base}-{normalized_quote}"
        return bare_symbol.strip().upper()

    @staticmethod
    def _looks_like_crypto_symbol(symbol: str) -> bool:
        if symbol.endswith("USDT") and len(symbol) >= 7:
            return True
        if symbol.endswith("USD") and len(symbol) >= 6:
            return True
        return False

    @staticmethod
    def _split_market_symbol(symbol: str) -> tuple[str | None, str]:
        value = symbol.strip()
        if ":" not in value:
            return None, value
        market, bare_symbol = value.split(":", 1)
        market = market.strip().upper()
        bare_symbol = bare_symbol.strip()
        if not market or not bare_symbol:
            return None, value
        return market, bare_symbol

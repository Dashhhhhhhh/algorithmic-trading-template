"""Local CSV market data provider for historical/backtest workflows."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.utils.errors import DataProviderError


class CsvDataClient:
    """Load OHLCV bars from local CSV files.

    Expected file patterns:
    - {SYMBOL}.csv
    - {symbol}.csv

    Required columns after normalization: open, high, low, close, volume.
    Date column can be one of: date, datetime, timestamp.
    """

    DATE_COL_CANDIDATES = ("date", "datetime", "timestamp")

    def __init__(self, data_dir: str = "historical_data") -> None:
        self.data_dir = Path(data_dir)

    def fetch_daily(self, symbol: str, adjusted: bool = False) -> pd.DataFrame:
        _ = adjusted  # CSV loader currently does not differentiate adjusted bars.
        path = self._resolve_path(symbol)
        if path is None:
            expected_paths = ", ".join(self._expected_csv_hints(symbol))
            raise DataProviderError(
                f"No CSV found for {symbol} in {self.data_dir}. "
                f"Expected one of: {expected_paths}"
            )

        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            raise DataProviderError(f"Failed to read CSV for {symbol}: {exc}") from exc

        frame = self._normalize_columns(frame=frame, symbol=symbol)
        return frame

    def _resolve_path(self, symbol: str) -> Path | None:
        market, raw_symbol = self._split_market_symbol(symbol)
        symbol_upper = raw_symbol.upper()
        symbol_lower = raw_symbol.lower()

        candidates: list[Path] = []
        if market is not None:
            market_upper = market.upper()
            market_lower = market.lower()
            candidates.extend(
                [
                    self.data_dir / market_upper / f"{symbol_upper}.csv",
                    self.data_dir / market_upper / f"{symbol_lower}.csv",
                    self.data_dir / market_lower / f"{symbol_upper}.csv",
                    self.data_dir / market_lower / f"{symbol_lower}.csv",
                ]
            )

        candidates.extend(
            [
                self.data_dir / f"{symbol_upper}.csv",
                self.data_dir / f"{symbol_lower}.csv",
            ]
        )

        seen: set[Path] = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            if path.exists():
                return path
        return None

    @staticmethod
    def _split_market_symbol(symbol: str) -> tuple[str | None, str]:
        normalized = symbol.strip()
        if ":" not in normalized:
            return None, normalized

        market, bare_symbol = normalized.split(":", 1)
        market = market.strip()
        bare_symbol = bare_symbol.strip()
        if not market or not bare_symbol:
            return None, normalized
        return market, bare_symbol

    def _expected_csv_hints(self, symbol: str) -> list[str]:
        market, raw_symbol = self._split_market_symbol(symbol)
        symbol_upper = raw_symbol.upper()
        hints = [f"{symbol_upper}.csv"]
        if market is not None:
            hints.insert(0, f"{market.upper()}/{symbol_upper}.csv")
        return hints

    def _normalize_columns(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        cols = {col.strip().lower(): col for col in frame.columns}

        date_col = None
        for candidate in self.DATE_COL_CANDIDATES:
            if candidate in cols:
                date_col = cols[candidate]
                break
        if date_col is None:
            raise DataProviderError(
                f"{symbol}: CSV missing date column. Use one of: "
                f"{', '.join(self.DATE_COL_CANDIDATES)}."
            )

        rename_map = {}
        for wanted in ("open", "high", "low", "close", "volume"):
            if wanted not in cols:
                raise DataProviderError(
                    f"{symbol}: CSV missing required column '{wanted}'."
                )
            rename_map[cols[wanted]] = wanted

        frame = frame.rename(columns=rename_map)
        try:
            frame.index = pd.to_datetime(frame[date_col], utc=False)
        except Exception as exc:
            raise DataProviderError(f"{symbol}: invalid date column values: {exc}") from exc

        frame = frame.sort_index()
        frame = frame[["open", "high", "low", "close", "volume"]]
        frame = frame.apply(pd.to_numeric, errors="coerce").dropna()
        if frame.empty:
            raise DataProviderError(f"{symbol}: CSV has no valid OHLCV rows after parsing.")
        return frame

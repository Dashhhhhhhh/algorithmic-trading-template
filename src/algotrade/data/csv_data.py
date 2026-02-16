"""CSV-backed market data provider."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class CsvDataProvider:
    """Load OHLCV bars from local CSV files."""

    date_column_candidates = ("date", "datetime", "timestamp")

    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)

    def get_bars(self, symbol: str) -> pd.DataFrame:
        path = self._resolve_path(symbol)
        if path is None:
            raise ValueError(f"No CSV found for {symbol} under {self.data_dir}")
        frame = pd.read_csv(path)
        return self._normalize(frame, symbol)

    def _resolve_path(self, symbol: str) -> Path | None:
        market, bare_symbol = self._split_market_symbol(symbol)
        symbol_upper = bare_symbol.upper()
        symbol_lower = bare_symbol.lower()
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
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _split_market_symbol(symbol: str) -> tuple[str | None, str]:
        value = symbol.strip()
        if ":" not in value:
            return None, value
        market, bare_symbol = value.split(":", 1)
        market = market.strip()
        bare_symbol = bare_symbol.strip()
        if not market or not bare_symbol:
            return None, value
        return market, bare_symbol

    def _normalize(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        lower_to_original = {column.strip().lower(): column for column in frame.columns}
        date_column = self._pick_date_column(lower_to_original)
        rename_map = self._build_ohlcv_rename_map(lower_to_original, symbol)
        normalized = frame.rename(columns=rename_map)
        normalized.index = pd.to_datetime(normalized[date_column], utc=False)
        normalized = normalized.sort_index()
        normalized = normalized[["open", "high", "low", "close", "volume"]]
        normalized = normalized.apply(pd.to_numeric, errors="coerce").dropna()
        if normalized.empty:
            raise ValueError(f"{symbol}: CSV has no valid OHLCV rows")
        return normalized

    def _pick_date_column(self, lower_to_original: dict[str, str]) -> str:
        for candidate in self.date_column_candidates:
            if candidate in lower_to_original:
                return lower_to_original[candidate]
        candidates = ", ".join(self.date_column_candidates)
        raise ValueError(f"CSV missing date column. Expected one of: {candidates}")

    @staticmethod
    def _build_ohlcv_rename_map(
        lower_to_original: dict[str, str],
        symbol: str,
    ) -> dict[str, str]:
        rename_map: dict[str, str] = {}
        for name in ("open", "high", "low", "close", "volume"):
            source = lower_to_original.get(name)
            if source is None:
                raise ValueError(f"{symbol}: CSV missing required column '{name}'")
            rename_map[source] = name
        return rename_map

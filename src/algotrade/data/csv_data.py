"""CSV-backed market data provider."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd


class CsvDataProvider:
    """Load OHLCV bars from local CSV files."""

    date_column_candidates = ("date", "datetime", "timestamp")

    def __init__(
        self,
        data_dir: str,
        walk_forward: bool = False,
        warmup_bars: int = 1,
        missing_data_fetcher: Callable[[str], pd.DataFrame] | None = None,
        persist_downloaded_bars: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.walk_forward = walk_forward
        self.warmup_bars = max(1, warmup_bars)
        self.missing_data_fetcher = missing_data_fetcher
        self.persist_downloaded_bars = persist_downloaded_bars
        self._bars_cache: dict[str, pd.DataFrame] = {}
        self._cursor_by_symbol: dict[str, int] = {}
        self._missing_data_errors: dict[str, str] = {}

    def get_bars(self, symbol: str) -> pd.DataFrame:
        bars = self._load_bars(symbol)
        if not self.walk_forward:
            return bars.copy()

        cursor = self._cursor_by_symbol.get(symbol)
        if cursor is None:
            cursor = min(self.warmup_bars, len(bars))
        end = max(1, min(cursor, len(bars)))
        if cursor < len(bars):
            self._cursor_by_symbol[symbol] = cursor + 1
        else:
            self._cursor_by_symbol[symbol] = len(bars)
        return bars.iloc[:end].copy()

    def walk_forward_total_steps(self, symbols: list[str]) -> int:
        """Return total walk-forward steps needed to traverse all symbol histories."""
        if not self.walk_forward:
            return 1
        step_counts: list[int] = []
        for symbol in symbols:
            bars = self._load_bars(symbol)
            initial_window = min(self.warmup_bars, len(bars))
            step_counts.append(max(1, len(bars) - initial_window + 1))
        return max(step_counts, default=1)

    def _load_bars(self, symbol: str) -> pd.DataFrame:
        cached = self._bars_cache.get(symbol)
        if cached is not None:
            return cached

        path = self._resolve_path(symbol)
        if path is None:
            fallback_bars = self._load_missing_data_with_fallback(symbol)
            if fallback_bars is None:
                raise ValueError(f"No CSV found for {symbol} under {self.data_dir}")
            self._bars_cache[symbol] = fallback_bars
            return fallback_bars
        frame = pd.read_csv(path)
        normalized = self._normalize_csv(frame, symbol)
        self._bars_cache[symbol] = normalized
        return normalized

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

    def _load_missing_data_with_fallback(self, symbol: str) -> pd.DataFrame | None:
        if self.missing_data_fetcher is None:
            return None

        previous_error = self._missing_data_errors.get(symbol)
        if previous_error is not None:
            raise ValueError(previous_error)

        try:
            frame = self.missing_data_fetcher(symbol)
        except Exception as exc:
            message = (
                f"No CSV found for {symbol} under {self.data_dir}; fallback fetch failed: {exc}"
            )
            self._missing_data_errors[symbol] = message
            raise ValueError(message) from exc

        if not isinstance(frame, pd.DataFrame):
            message = (
                f"No CSV found for {symbol} under {self.data_dir}; "
                "fallback fetcher returned a non-DataFrame result"
            )
            self._missing_data_errors[symbol] = message
            raise ValueError(message)

        normalized = self._normalize_fallback(frame, symbol)
        if self.persist_downloaded_bars:
            self._persist_downloaded_bars(symbol, normalized)
        return normalized

    def _persist_downloaded_bars(self, symbol: str, bars: pd.DataFrame) -> None:
        path = self._preferred_save_path(symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        output = bars.reset_index()
        first_column = str(output.columns[0])
        if first_column != "date":
            output = output.rename(columns={first_column: "date"})
        output.to_csv(path, index=False)

    def _preferred_save_path(self, symbol: str) -> Path:
        market, bare_symbol = self._split_market_symbol(symbol)
        normalized_symbol = bare_symbol.upper()
        if market is None:
            return self.data_dir / f"{normalized_symbol}.csv"
        return self.data_dir / market.upper() / f"{normalized_symbol}.csv"

    def _normalize_csv(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        lower_to_original = {column.strip().lower(): column for column in frame.columns}
        date_column = self._pick_date_column(lower_to_original)
        rename_map = self._build_ohlcv_rename_map(lower_to_original, symbol)
        normalized = frame.rename(columns=rename_map)
        normalized.index = pd.to_datetime(normalized[date_column], utc=False)
        return self._normalize_ohlcv(normalized, symbol)

    def _normalize_fallback(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        normalized = frame.copy()
        if isinstance(normalized.index, pd.DatetimeIndex):
            normalized.index = pd.to_datetime(normalized.index, utc=False)
        else:
            lower_to_original = {column.strip().lower(): column for column in normalized.columns}
            date_column = self._pick_date_column(lower_to_original)
            normalized.index = pd.to_datetime(normalized[date_column], utc=False)
        return self._normalize_ohlcv(normalized, symbol)

    def _normalize_ohlcv(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        lower_to_original = {column.strip().lower(): column for column in frame.columns}
        rename_map = self._build_ohlcv_rename_map(lower_to_original, symbol)
        normalized = frame.rename(columns=rename_map)
        normalized = normalized.sort_index()
        normalized = normalized[["open", "high", "low", "close", "volume"]].copy()
        normalized = normalized.apply(pd.to_numeric, errors="coerce")
        normalized = normalized.dropna(subset=["open", "high", "low", "close"])
        normalized["volume"] = normalized["volume"].fillna(0.0)
        normalized = normalized.dropna()
        if normalized.empty:
            raise ValueError(f"{symbol}: data has no valid OHLCV rows")
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

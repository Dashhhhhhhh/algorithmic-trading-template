"""Environment and CLI runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Self

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from algotrade.domain.models import Mode

DEFAULT_STOCK_UNIVERSE = ["SPY"]
DEFAULT_CRYPTO_UNIVERSE = ["BTCUSD"]


def parse_bool(value: str | None, default: bool) -> bool:
    """Parse truthy environment strings."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_optional_positive_int(value: str | None) -> int | None:
    """Parse optional positive integer values from env strings."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    parsed = int(text)
    if parsed <= 0:
        raise ValueError("cycles must be positive")
    return parsed


def parse_symbols(value: str | None, default: list[str] | None = None) -> list[str]:
    """Parse comma-separated symbols."""
    fallback = default or ["SPY"]
    if not value:
        return list(fallback)
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    return symbols or list(fallback)


def dedupe_symbols(symbols: list[str]) -> list[str]:
    """Remove duplicate symbols while preserving order."""
    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol in seen:
            continue
        seen.add(symbol)
        deduped.append(symbol)
    return deduped


def normalize_asset_universe(value: str | None, default: str = "stocks") -> str:
    """Normalize asset universe selector values."""
    mapping = {
        "stock": "stocks",
        "stocks": "stocks",
        "crypto": "crypto",
        "cryptos": "crypto",
        "all": "all",
        "both": "all",
        "mixed": "all",
    }
    normalized_default = mapping.get(default.strip().lower(), "stocks")
    if value is None:
        return normalized_default
    candidate = value.strip().lower()
    return mapping.get(candidate, normalized_default)


def resolve_symbol_universe(
    explicit_symbols: str | None,
    universe_selection: str | None,
    stock_universe: str | None,
    crypto_universe: str | None,
) -> list[str]:
    """Resolve the final tradable symbol list from universe-style env vars."""
    if explicit_symbols and explicit_symbols.strip():
        return parse_symbols(explicit_symbols)

    selected_universe = normalize_asset_universe(universe_selection, default="stocks")
    stock_symbols = parse_symbols(stock_universe, default=DEFAULT_STOCK_UNIVERSE)
    crypto_symbols = parse_symbols(crypto_universe, default=DEFAULT_CRYPTO_UNIVERSE)

    if selected_universe == "crypto":
        return crypto_symbols
    if selected_universe == "all":
        return dedupe_symbols([*stock_symbols, *crypto_symbols])
    return stock_symbols


def normalize_mode(value: str | None, default: Mode = "live") -> Mode:
    """Normalize runtime mode while mapping legacy paper mode to live."""
    candidate = (value or default).strip().lower()
    if candidate == "paper":
        return "live"
    if candidate in {"backtest", "live"}:
        return candidate
    return default


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    mode: Mode = "live"
    strategy: str = "sma_crossover"
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    cycles: int | None = None
    interval_seconds: int = 5
    data_source: str = "auto"
    historical_data_dir: str = "historical_data"
    events_dir: str = "runs"
    state_db_path: str = "state/algotrade_state.db"
    log_level: str = "INFO"
    default_order_type: str = "market"
    order_qty: int = 1
    allow_short: bool = True
    max_abs_position_per_symbol: int = 100
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    timeframe: str = "1Day"
    backtest_starting_cash: float = 100000.0
    sma_short_window: int = 20
    sma_long_window: int = 50
    momentum_lookback_bars: int = 10
    momentum_threshold: float = 0.01
    momentum_max_abs_qty: int = 2
    scalping_lookback_bars: int = 2
    scalping_threshold: float = 0.05
    scalping_max_abs_qty: int = 1
    scalping_flip_seconds: int = 1
    scalping_allow_short: bool = False

    @classmethod
    def from_env(cls) -> Self:
        """Create settings from environment variables."""
        if load_dotenv is not None:
            load_dotenv()
        mode = normalize_mode(os.getenv("MODE"), default="live")
        symbols = resolve_symbol_universe(
            explicit_symbols=os.getenv("SYMBOLS"),
            universe_selection=os.getenv("ASSET_UNIVERSE"),
            stock_universe=os.getenv("STOCK_UNIVERSE"),
            crypto_universe=os.getenv("CRYPTO_UNIVERSE"),
        )
        raw = cls(
            mode=mode,
            strategy=str(os.getenv("STRATEGY", "sma_crossover")).strip(),
            symbols=symbols,
            cycles=parse_optional_positive_int(os.getenv("CYCLES")),
            interval_seconds=int(
                os.getenv("INTERVAL_SECONDS") or os.getenv("POLLING_INTERVAL_SECONDS", "5")
            ),
            data_source=str(os.getenv("DATA_SOURCE", "auto")).strip().lower(),
            historical_data_dir=str(os.getenv("HISTORICAL_DATA_DIR", "historical_data")).strip(),
            events_dir=str(os.getenv("EVENTS_DIR", "runs")).strip(),
            state_db_path=str(os.getenv("STATE_DB_PATH", "state/algotrade_state.db")).strip(),
            log_level=str(os.getenv("LOG_LEVEL", "INFO")).strip().upper(),
            default_order_type=str(os.getenv("DEFAULT_ORDER_TYPE", "market")).strip(),
            order_qty=int(os.getenv("ORDER_QTY", "1")),
            allow_short=parse_bool(os.getenv("ALLOW_SHORT"), True),
            max_abs_position_per_symbol=int(os.getenv("MAX_ABS_POSITION_PER_SYMBOL", "100")),
            alpaca_api_key=str(os.getenv("ALPACA_API_KEY", "")).strip(),
            alpaca_secret_key=str(os.getenv("ALPACA_SECRET_KEY", "")).strip(),
            alpaca_base_url=str(
                os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
            ).strip(),
            alpaca_data_url=str(
                os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
            ).strip(),
            timeframe=str(os.getenv("TIMEFRAME", "1Day")).strip(),
            backtest_starting_cash=float(os.getenv("BACKTEST_STARTING_CASH", "100000")),
            sma_short_window=int(os.getenv("SMA_SHORT_WINDOW", "20")),
            sma_long_window=int(os.getenv("SMA_LONG_WINDOW", "50")),
            momentum_lookback_bars=int(os.getenv("MOMENTUM_LOOKBACK_BARS", "10")),
            momentum_threshold=float(os.getenv("MOMENTUM_THRESHOLD", "0.01")),
            momentum_max_abs_qty=int(os.getenv("MOMENTUM_MAX_ABS_QTY", "2")),
            scalping_lookback_bars=int(os.getenv("SCALPING_LOOKBACK_BARS", "2")),
            scalping_threshold=float(os.getenv("SCALPING_THRESHOLD", "0.05")),
            scalping_max_abs_qty=int(os.getenv("SCALPING_MAX_ABS_QTY", "1")),
            scalping_flip_seconds=int(os.getenv("SCALPING_FLIP_SECONDS", "1")),
            scalping_allow_short=parse_bool(os.getenv("SCALPING_ALLOW_SHORT"), False),
        )
        return raw.validate()

    def with_overrides(self, **kwargs: object) -> Self:
        """Return a new settings object with updated values."""
        overrides = dict(kwargs)
        mode_override = overrides.get("mode")
        if isinstance(mode_override, str):
            overrides["mode"] = normalize_mode(mode_override, default=self.mode)
        updated = replace(self, **overrides)
        return updated.validate()

    def cycle_limit(self) -> int | None:
        """Return finite cycle count or None for infinite execution."""
        if self.cycles is not None:
            return self.cycles
        if self.mode == "backtest":
            return 1
        return None

    def effective_data_source(self) -> str:
        """Resolve mode-aware data source defaults."""
        if self.data_source in {"alpaca", "csv"}:
            return self.data_source
        if self.mode == "backtest":
            return "csv"
        return "alpaca"

    def validate(self) -> Self:
        """Validate settings fields."""
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.cycles is not None and self.cycles <= 0:
            raise ValueError("cycles must be positive")
        if self.order_qty <= 0:
            raise ValueError("order_qty must be positive")
        if self.max_abs_position_per_symbol <= 0:
            raise ValueError("max_abs_position_per_symbol must be positive")
        if self.sma_short_window <= 0 or self.sma_long_window <= 0:
            raise ValueError("SMA windows must be positive")
        if self.sma_short_window >= self.sma_long_window:
            raise ValueError("sma_short_window must be less than sma_long_window")
        if self.momentum_lookback_bars <= 0:
            raise ValueError("momentum_lookback_bars must be positive")
        if self.momentum_max_abs_qty <= 0:
            raise ValueError("momentum_max_abs_qty must be positive")
        if self.momentum_threshold < 0:
            raise ValueError("momentum_threshold must be non-negative")
        if self.scalping_lookback_bars <= 0:
            raise ValueError("scalping_lookback_bars must be positive")
        if self.scalping_max_abs_qty <= 0:
            raise ValueError("scalping_max_abs_qty must be positive")
        if self.scalping_threshold < 0:
            raise ValueError("scalping_threshold must be non-negative")
        if self.scalping_flip_seconds < 0:
            raise ValueError("scalping_flip_seconds must be non-negative")
        if self.mode not in {"backtest", "live"}:
            raise ValueError("mode must be one of backtest, live")
        if self.data_source not in {"auto", "alpaca", "csv"}:
            raise ValueError("data_source must be one of auto, alpaca, csv")
        return self

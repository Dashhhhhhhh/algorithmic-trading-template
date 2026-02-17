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


def parse_bool(value: str | None, default: bool) -> bool:
    """Parse truthy environment strings."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_symbols(value: str | None, default: list[str] | None = None) -> list[str]:
    """Parse comma-separated symbols."""
    fallback = default or ["SPY"]
    if not value:
        return list(fallback)
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    return symbols or list(fallback)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    mode: Mode = "paper"
    strategy: str = "sma_crossover"
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    once: bool = False
    continuous: bool = False
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

    @classmethod
    def from_env(cls) -> Self:
        """Create settings from environment variables."""
        if load_dotenv is not None:
            load_dotenv()
        mode = str(os.getenv("MODE", "paper")).strip().lower()
        raw = cls(
            mode=mode if mode in {"backtest", "paper", "live"} else "paper",
            strategy=str(os.getenv("STRATEGY", "sma_crossover")).strip(),
            symbols=parse_symbols(os.getenv("SYMBOLS")),
            once=parse_bool(os.getenv("ONCE"), False),
            continuous=parse_bool(os.getenv("CONTINUOUS"), False),
            interval_seconds=int(os.getenv("INTERVAL_SECONDS", "5")),
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
        )
        return raw.validate()

    def with_overrides(self, **kwargs: object) -> Self:
        """Return a new settings object with updated values."""
        updated = replace(self, **kwargs)
        return updated.validate()

    def should_run_continuously(self) -> bool:
        """Resolve once versus continuous behavior."""
        if self.once:
            return False
        if self.continuous:
            return True
        return self.mode in {"paper", "live"}

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
        if self.mode not in {"backtest", "paper", "live"}:
            raise ValueError("mode must be one of backtest, paper, live")
        if self.data_source not in {"auto", "alpaca", "csv"}:
            raise ValueError("data_source must be one of auto, alpaca, csv")
        return self

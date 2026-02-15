"""Environment-driven app configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Self

from app.utils.errors import ConfigError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_symbols(value: str | None) -> list[str]:
    if not value:
        return ["SPY"]
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    return symbols or ["SPY"]


def _strategy_symbols_env_var(strategy_name: str) -> str:
    normalized = strategy_name.strip().upper().replace("-", "_")
    return f"{normalized}_SYMBOLS"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    data_source: str = "alpaca"
    historical_data_dir: str = "historical_data"
    alpaca_data_url: str = "https://data.alpaca.markets"
    timeframe: str = "1D"
    strategy: str = "sma_crossover"
    dry_run: bool = True
    allow_short: bool = True
    log_level: str = "INFO"
    log_file: str | None = None
    order_qty: int = 1
    loop_interval_seconds: int = 5
    backtest_starting_cash: float = 100000.0
    sma_short_window: int = 20
    sma_long_window: int = 50
    hft_momentum_window: int = 3
    hft_volatility_window: int = 12
    hft_min_volatility: float = 0.0005
    hft_flip_seconds: int = 3

    def symbols_for_strategy(self, strategy_name: str) -> list[str]:
        """Resolve symbols for a strategy from <STRATEGY_NAME>_SYMBOLS, with SYMBOLS fallback."""
        strategy_symbols = os.getenv(_strategy_symbols_env_var(strategy_name))
        if strategy_symbols is None or not strategy_symbols.strip():
            return list(self.symbols)
        return _parse_symbols(strategy_symbols)

    @classmethod
    def from_env(cls) -> Self:
        """Build settings from environment variables."""
        if load_dotenv is not None:
            load_dotenv()

        try:
            settings = cls(
                alpaca_api_key=os.getenv("ALPACA_API_KEY", "").strip(),
                alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
                alpaca_base_url=os.getenv(
                    "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
                ).strip(),
                symbols=_parse_symbols(os.getenv("SYMBOLS")),
                data_source=os.getenv("DATA_SOURCE", "alpaca").strip().lower(),
                historical_data_dir=os.getenv("HISTORICAL_DATA_DIR", "historical_data").strip(),
                alpaca_data_url=os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").strip(),
                timeframe=os.getenv("TIMEFRAME", "1D").strip(),
                strategy=os.getenv("STRATEGY", "sma_crossover").strip(),
                dry_run=_parse_bool(os.getenv("DRY_RUN"), default=True),
                allow_short=_parse_bool(os.getenv("ALLOW_SHORT"), default=True),
                log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
                log_file=os.getenv("LOG_FILE", "").strip() or None,
                order_qty=int(os.getenv("ORDER_QTY", "1")),
                loop_interval_seconds=int(os.getenv("LOOP_INTERVAL_SECONDS", "5")),
                backtest_starting_cash=float(os.getenv("BACKTEST_STARTING_CASH", "100000")),
                sma_short_window=int(os.getenv("SMA_SHORT_WINDOW", "20")),
                sma_long_window=int(os.getenv("SMA_LONG_WINDOW", "50")),
                hft_momentum_window=int(os.getenv("HFT_MOMENTUM_WINDOW", "3")),
                hft_volatility_window=int(os.getenv("HFT_VOLATILITY_WINDOW", "12")),
                hft_min_volatility=float(os.getenv("HFT_MIN_VOLATILITY", "0.0005")),
                hft_flip_seconds=int(os.getenv("HFT_FLIP_SECONDS", "3")),
            )
        except ValueError as exc:
            raise ConfigError(
                "One or more numeric environment variables are invalid. "
                "Check ORDER_QTY, SMA_*, and HFT_* values in your .env file."
            ) from exc

        return settings.validate()

    def validate(self) -> Self:
        """Validate loaded settings and raise clear config errors."""
        if self.order_qty <= 0:
            raise ConfigError("ORDER_QTY must be a positive integer.")

        if self.loop_interval_seconds <= 0:
            raise ConfigError("LOOP_INTERVAL_SECONDS must be a positive integer.")

        if self.backtest_starting_cash <= 0:
            raise ConfigError("BACKTEST_STARTING_CASH must be a positive number.")

        if self.sma_short_window <= 0 or self.sma_long_window <= 0:
            raise ConfigError("SMA window values must be positive integers.")

        if self.sma_short_window >= self.sma_long_window:
            raise ConfigError(
                "SMA_SHORT_WINDOW must be less than SMA_LONG_WINDOW "
                "(example: 20 and 50)."
            )

        if self.hft_momentum_window <= 0 or self.hft_volatility_window <= 0:
            raise ConfigError("HFT window values must be positive integers.")

        if self.hft_flip_seconds <= 0:
            raise ConfigError("HFT_FLIP_SECONDS must be a positive integer.")

        if self.hft_min_volatility < 0:
            raise ConfigError("HFT_MIN_VOLATILITY cannot be negative.")

        if self.data_source not in {"alpaca", "csv"}:
            raise ConfigError(
                "DATA_SOURCE must be one of: alpaca, csv."
            )

        return self

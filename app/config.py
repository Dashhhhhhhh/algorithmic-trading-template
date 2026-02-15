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


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    alpha_vantage_api_key: str
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    timeframe: str = "1D"
    strategy: str = "sma_crossover"
    dry_run: bool = True
    log_level: str = "INFO"
    log_file: str | None = None
    order_qty: int = 1
    sma_short_window: int = 20
    sma_long_window: int = 50

    @classmethod
    def from_env(cls) -> Self:
        """Build settings from environment variables."""
        if load_dotenv is not None:
            load_dotenv()

        return cls(
            alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY", "").strip(),
            alpaca_api_key=os.getenv("ALPACA_API_KEY", "").strip(),
            alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
            alpaca_base_url=os.getenv(
                "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
            ).strip(),
            symbols=_parse_symbols(os.getenv("SYMBOLS")),
            timeframe=os.getenv("TIMEFRAME", "1D").strip(),
            strategy=os.getenv("STRATEGY", "sma_crossover").strip(),
            dry_run=_parse_bool(os.getenv("DRY_RUN"), default=True),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_file=os.getenv("LOG_FILE", "").strip() or None,
            order_qty=int(os.getenv("ORDER_QTY", "1")),
            sma_short_window=int(os.getenv("SMA_SHORT_WINDOW", "20")),
            sma_long_window=int(os.getenv("SMA_LONG_WINDOW", "50")),
        ).validate()

    def validate(self) -> Self:
        """Validate loaded settings and raise clear config errors."""
        missing: list[str] = []

        if not self.alpha_vantage_api_key:
            missing.append("ALPHA_VANTAGE_API_KEY")
        if not self.alpaca_api_key:
            missing.append("ALPACA_API_KEY")
        if not self.alpaca_secret_key:
            missing.append("ALPACA_SECRET_KEY")

        if missing:
            vars_text = ", ".join(missing)
            raise ConfigError(
                f"Missing required environment variable(s): {vars_text}. "
                "Create a .env from .env.example and try again."
            )

        if self.order_qty <= 0:
            raise ConfigError("ORDER_QTY must be a positive integer.")

        if self.sma_short_window <= 0 or self.sma_long_window <= 0:
            raise ConfigError("SMA window values must be positive integers.")

        if self.sma_short_window >= self.sma_long_window:
            raise ConfigError(
                "SMA_SHORT_WINDOW must be less than SMA_LONG_WINDOW "
                "(example: 20 and 50)."
            )

        return self

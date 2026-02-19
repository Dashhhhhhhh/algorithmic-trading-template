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


def parse_optional_positive_int(value: str | None, *, field_name: str) -> int | None:
    """Parse optional positive integer values from env strings."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    parsed = int(text)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
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
    strategy: str = ""
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    max_passes: int | None = None
    backtest_max_steps: int | None = None
    interval_seconds: int = 5
    data_source: str = "auto"
    historical_data_dir: str = "historical_data"
    events_dir: str = "runs"
    state_db_path: str = "state/algotrade_state.db"
    log_level: str = "INFO"
    default_order_type: str = "market"
    order_sizing_method: str = "notional"
    order_notional_usd: float = 100.0
    min_trade_qty: float = 0.0001
    qty_precision: int = 6
    allow_short: bool = True
    max_abs_position_per_symbol: float = 100.0
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    timeframe: str = "1Day"
    backtest_starting_cash: float = 100000.0

    @classmethod
    def from_env(cls) -> Self:
        """Create settings from environment variables."""
        if load_dotenv is not None:
            load_dotenv()
        mode = normalize_mode(os.getenv("MODE"), default="live")
        max_passes = parse_optional_positive_int(
            os.getenv("MAX_PASSES"),
            field_name="max_passes",
        )
        if max_passes is None and mode == "live":
            # Legacy alias for live mode only.
            max_passes = parse_optional_positive_int(
                os.getenv("CYCLES"),
                field_name="cycles",
            )
        strategy = str(os.getenv("STRATEGY", "")).strip()
        symbols = resolve_symbol_universe(
            explicit_symbols=os.getenv("SYMBOLS"),
            universe_selection=os.getenv("ASSET_UNIVERSE"),
            stock_universe=os.getenv("STOCK_UNIVERSE"),
            crypto_universe=os.getenv("CRYPTO_UNIVERSE"),
        )
        raw = cls(
            mode=mode,
            strategy=strategy,
            symbols=symbols,
            max_passes=max_passes,
            backtest_max_steps=parse_optional_positive_int(
                os.getenv("BACKTEST_MAX_STEPS"),
                field_name="backtest_max_steps",
            ),
            interval_seconds=int(
                os.getenv("INTERVAL_SECONDS") or os.getenv("POLLING_INTERVAL_SECONDS", "5")
            ),
            data_source=str(os.getenv("DATA_SOURCE", "auto")).strip().lower(),
            historical_data_dir=str(os.getenv("HISTORICAL_DATA_DIR", "historical_data")).strip(),
            events_dir=str(os.getenv("EVENTS_DIR", "runs")).strip(),
            state_db_path=str(os.getenv("STATE_DB_PATH", "state/algotrade_state.db")).strip(),
            log_level=str(os.getenv("LOG_LEVEL", "INFO")).strip().upper(),
            default_order_type=str(os.getenv("DEFAULT_ORDER_TYPE", "market")).strip(),
            order_sizing_method=str(os.getenv("ORDER_SIZING_METHOD", "notional")).strip().lower(),
            order_notional_usd=float(os.getenv("ORDER_NOTIONAL_USD", "100")),
            min_trade_qty=float(os.getenv("MIN_TRADE_QTY", "0.0001")),
            qty_precision=int(os.getenv("QTY_PRECISION", "6")),
            allow_short=parse_bool(os.getenv("ALLOW_SHORT"), True),
            max_abs_position_per_symbol=float(os.getenv("MAX_ABS_POSITION_PER_SYMBOL", "100")),
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

    def live_pass_limit(self) -> int | None:
        """Return finite live pass count, or None for continuous execution."""
        return self.max_passes

    def backtest_step_cap(self) -> int | None:
        """Return optional backtest step cap."""
        return self.backtest_max_steps

    def cycle_limit(self) -> int | None:
        """Backward-compatible alias for legacy finite-run semantics."""
        return self.live_pass_limit()

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
        if self.max_passes is not None and self.max_passes <= 0:
            raise ValueError("max_passes must be positive")
        if self.backtest_max_steps is not None and self.backtest_max_steps <= 0:
            raise ValueError("backtest_max_steps must be positive")
        if self.order_sizing_method not in {"units", "notional"}:
            raise ValueError("order_sizing_method must be one of units, notional")
        if self.order_notional_usd <= 0:
            raise ValueError("order_notional_usd must be positive")
        if self.min_trade_qty <= 0:
            raise ValueError("min_trade_qty must be positive")
        if self.qty_precision < 0 or self.qty_precision > 12:
            raise ValueError("qty_precision must be between 0 and 12")
        if self.max_abs_position_per_symbol <= 0:
            raise ValueError("max_abs_position_per_symbol must be positive")
        if self.mode not in {"backtest", "live"}:
            raise ValueError("mode must be one of backtest, live")
        if self.mode == "backtest" and self.max_passes is not None:
            raise ValueError("max_passes is only valid in live mode")
        if self.mode == "live" and self.backtest_max_steps is not None:
            raise ValueError("backtest_max_steps is only valid in backtest mode")
        if self.data_source not in {"auto", "alpaca", "csv"}:
            raise ValueError("data_source must be one of auto, alpaca, csv")
        return self

"""Custom exceptions for clearer error handling across the app."""


class TradingAppError(Exception):
    """Base exception for all app-specific errors."""


class ConfigError(TradingAppError):
    """Raised when environment configuration is invalid or missing."""


class DataProviderError(TradingAppError):
    """Raised when market data retrieval fails."""


class BrokerError(TradingAppError):
    """Raised when broker API operations fail."""


class StrategyError(TradingAppError):
    """Raised when a strategy cannot compute a valid signal."""


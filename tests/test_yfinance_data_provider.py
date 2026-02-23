from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from algotrade.data.yfinance_data import YFinanceDataProvider


def test_yfinance_symbol_mapping_supports_stocks_and_crypto() -> None:
    assert YFinanceDataProvider._resolve_yfinance_symbol("SPY") == "SPY"
    assert YFinanceDataProvider._resolve_yfinance_symbol("BTCUSD") == "BTC-USD"
    assert YFinanceDataProvider._resolve_yfinance_symbol("CRYPTO:ETHUSDT") == "ETH-USD"


def test_yfinance_timeframe_normalization() -> None:
    assert YFinanceDataProvider._normalize_interval("1Day") == "1d"
    assert YFinanceDataProvider._normalize_interval("1Hour") == "60m"
    assert YFinanceDataProvider._normalize_interval("15Min") == "15m"
    assert YFinanceDataProvider._period_for_interval("1m") == "7d"
    assert YFinanceDataProvider._period_for_interval("60m") == "60d"
    assert YFinanceDataProvider._period_for_interval("1d") == "max"


def test_yfinance_provider_normalizes_history(monkeypatch) -> None:
    captured = {"ticker": None}
    history = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.0, 10.0],
            "Close": [10.5, 11.5],
        },
        index=pd.to_datetime(["2025-01-01", "2025-01-02"]),
    )

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            captured["ticker"] = ticker

        def history(self, **_kwargs: str) -> pd.DataFrame:
            return history

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=FakeTicker))
    provider = YFinanceDataProvider(timeframe="1Day")

    bars = provider.get_bars("BTCUSD")

    assert captured["ticker"] == "BTC-USD"
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert float(bars["volume"].iloc[-1]) == 0.0
    assert float(bars["close"].iloc[-1]) == 11.5


def test_yfinance_provider_normalizes_mixed_timezone_offsets_to_utc(monkeypatch) -> None:
    history = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.0, 10.0],
            "Close": [10.5, 11.5],
        },
        index=[
            "2025-01-02T09:30:00-05:00",
            "2025-07-02T09:30:00-04:00",
        ],
    )

    class FakeTicker:
        def __init__(self, _ticker: str) -> None:
            return None

        def history(self, **_kwargs: str) -> pd.DataFrame:
            return history

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=FakeTicker))
    provider = YFinanceDataProvider(timeframe="1Day")

    bars = provider.get_bars("SPY")

    assert bars.index.tz is not None
    assert str(bars.index.tz) == "UTC"

"""Tests for simple backtest runner."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.backtest import run_backtest_for_symbol
from app.data.csv_data import CsvDataClient
from app.strategy.base import Signal, Strategy


class _AlwaysBuyStrategy(Strategy):
    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        _ = symbol, bars
        return Signal.BUY


class _TrendStrategy(Strategy):
    def generate_signal(self, symbol: str, bars: pd.DataFrame) -> Signal:
        _ = symbol
        if len(bars) < 2:
            return Signal.HOLD
        return Signal.BUY if bars["close"].iloc[-1] >= bars["close"].iloc[-2] else Signal.SELL


def test_backtest_executes_trades() -> None:
    bars = pd.DataFrame(
        {
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100, 101, 102, 103],
            "volume": [1000, 1000, 1000, 1000],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
    )

    result = run_backtest_for_symbol(
        symbol="SPY",
        bars=bars,
        strategy=_AlwaysBuyStrategy(),
        qty=1,
        allow_short=True,
        starting_cash=1000.0,
    )
    assert result.trades >= 1
    assert result.end_equity > 0


def test_backtest_handles_multiple_markets_from_csv(tmp_path: Path) -> None:
    equities_dir = tmp_path / "EQUITIES"
    crypto_dir = tmp_path / "CRYPTO"
    equities_dir.mkdir()
    crypto_dir.mkdir()

    (equities_dir / "SPY.csv").write_text(
        "\n".join(
            [
                "date,open,high,low,close,volume",
                "2026-01-01,100,101,99,100,1000",
                "2026-01-02,100,102,99,101,1001",
                "2026-01-03,101,103,100,102,1002",
                "2026-01-04,102,104,101,101,1003",
                "2026-01-05,101,103,100,103,1004",
                "2026-01-06,103,105,102,104,1005",
            ]
        )
    )
    (crypto_dir / "BTCUSD.csv").write_text(
        "\n".join(
            [
                "date,open,high,low,close,volume",
                "2026-01-01,43000,43300,42900,43100,2100",
                "2026-01-02,43100,43800,43000,43700,2000",
                "2026-01-03,43700,44000,43300,43400,2200",
                "2026-01-04,43400,44500,43200,44300,2500",
                "2026-01-05,44300,44600,43900,44100,2300",
                "2026-01-06,44100,44800,44000,44700,2600",
            ]
        )
    )

    client = CsvDataClient(data_dir=str(tmp_path))
    symbols = ["EQUITIES:SPY", "CRYPTO:BTCUSD"]

    results = [
        run_backtest_for_symbol(
            symbol=symbol,
            bars=client.fetch_daily(symbol),
            strategy=_TrendStrategy(),
            qty=1,
            allow_short=True,
            starting_cash=5000.0,
        )
        for symbol in symbols
    ]

    assert [result.symbol for result in results] == symbols
    assert all(result.trades > 0 for result in results)

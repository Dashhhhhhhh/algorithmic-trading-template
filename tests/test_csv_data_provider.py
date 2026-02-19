from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from algotrade.data.csv_data import CsvDataProvider


def _write_csv(path: Path) -> None:
    frame = pd.DataFrame(
        {
            "date": [
                "2025-01-01",
                "2025-01-02",
                "2025-01-03",
                "2025-01-04",
            ],
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1000.0, 1100.0, 1200.0, 1300.0],
        }
    )
    frame.to_csv(path, index=False)


def test_csv_provider_non_walk_forward_returns_full_history(tmp_path: Path) -> None:
    path = tmp_path / "SPY.csv"
    _write_csv(path)
    provider = CsvDataProvider(data_dir=str(tmp_path))

    first = provider.get_bars("SPY")
    second = provider.get_bars("SPY")

    assert len(first) == 4
    assert len(second) == 4
    assert float(first["close"].iloc[-1]) == 103.5
    assert float(second["close"].iloc[-1]) == 103.5


def test_csv_provider_walk_forward_advances_until_end(tmp_path: Path) -> None:
    path = tmp_path / "SPY.csv"
    _write_csv(path)
    provider = CsvDataProvider(data_dir=str(tmp_path), walk_forward=True, warmup_bars=2)

    first = provider.get_bars("SPY")
    second = provider.get_bars("SPY")
    third = provider.get_bars("SPY")
    fourth = provider.get_bars("SPY")
    fifth = provider.get_bars("SPY")

    assert [len(first), len(second), len(third), len(fourth), len(fifth)] == [2, 3, 4, 4, 4]
    assert float(first["close"].iloc[-1]) == 101.5
    assert float(second["close"].iloc[-1]) == 102.5
    assert float(third["close"].iloc[-1]) == 103.5


def _fallback_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [30000.0, 30100.0],
            "high": [30150.0, 30200.0],
            "low": [29950.0, 30000.0],
            "close": [30100.0, 30180.0],
            "volume": [10.0, 12.0],
        },
        index=pd.to_datetime(["2025-01-01", "2025-01-02"]),
    )


def test_csv_provider_uses_fallback_fetcher_and_persists(tmp_path: Path) -> None:
    calls = {"count": 0}

    def fetcher(symbol: str) -> pd.DataFrame:
        calls["count"] += 1
        assert symbol == "BTCUSD"
        return _fallback_bars()

    provider = CsvDataProvider(data_dir=str(tmp_path), missing_data_fetcher=fetcher)

    first = provider.get_bars("BTCUSD")
    second = provider.get_bars("BTCUSD")

    assert len(first) == 2
    assert len(second) == 2
    assert float(second["close"].iloc[-1]) == 30180.0
    assert calls["count"] == 1
    assert (tmp_path / "BTCUSD.csv").exists()


def test_csv_provider_persists_market_prefixed_symbols(tmp_path: Path) -> None:
    provider = CsvDataProvider(
        data_dir=str(tmp_path),
        missing_data_fetcher=lambda _symbol: _fallback_bars(),
    )

    bars = provider.get_bars("CRYPTO:BTCUSD")

    assert len(bars) == 2
    assert (tmp_path / "CRYPTO" / "BTCUSD.csv").exists()


def test_csv_provider_reports_fallback_error_once(tmp_path: Path) -> None:
    calls = {"count": 0}

    def failing_fetcher(_symbol: str) -> pd.DataFrame:
        calls["count"] += 1
        raise RuntimeError("service unavailable")

    provider = CsvDataProvider(data_dir=str(tmp_path), missing_data_fetcher=failing_fetcher)

    with pytest.raises(ValueError, match="fallback fetch failed"):
        provider.get_bars("BTCUSD")
    with pytest.raises(ValueError, match="fallback fetch failed"):
        provider.get_bars("BTCUSD")

    assert calls["count"] == 1

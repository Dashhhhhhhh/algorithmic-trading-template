from __future__ import annotations

from pathlib import Path

import pandas as pd

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

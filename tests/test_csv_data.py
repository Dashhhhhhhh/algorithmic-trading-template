"""Tests for local CSV data provider."""

from __future__ import annotations

from pathlib import Path

from app.data.csv_data import CsvDataClient


def test_csv_loader_parses_ohlcv(tmp_path: Path) -> None:
    csv_path = tmp_path / "SPY.csv"
    csv_path.write_text(
        "\n".join(
            [
                "date,open,high,low,close,volume",
                "2026-01-02,100,101,99,100.5,1000000",
                "2026-01-03,100.5,102,100,101.5,1100000",
            ]
        )
    )

    client = CsvDataClient(data_dir=str(tmp_path))
    frame = client.fetch_daily("SPY")

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert float(frame["close"].iloc[-1]) == 101.5


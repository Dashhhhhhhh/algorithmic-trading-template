"""JSONL event sink and per-run Plotly report generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px

from algotrade.domain.events import TradeEvent


class JsonlEventSink:
    """Append-only JSONL writer."""

    def __init__(self, path: str) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = output_path

    def emit(self, event: TradeEvent) -> None:
        record = event.to_record()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")


def load_events(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL records from disk."""
    records: list[dict[str, Any]] = []
    input_path = Path(path)
    if not input_path.exists():
        return records
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            records.append(json.loads(text))
    return records


def generate_plotly_report(events_jsonl_path: str, output_html_path: str) -> None:
    """Render a simple interactive event timeline report."""
    events = load_events(events_jsonl_path)
    output = Path(output_html_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not events:
        empty_df = pd.DataFrame(
            {
                "ts": ["no-events"],
                "event_type": ["none"],
                "count": [0],
            }
        )
        figure = px.bar(empty_df, x="event_type", y="count", title="Run Event Summary")
        figure.write_html(str(output), include_plotlyjs="cdn")
        return

    rows: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload", {})
        rows.append(
            {
                "ts": event.get("ts"),
                "event_type": event.get("event_type"),
                "symbol": payload.get("symbol", ""),
                "value": payload.get("qty", 1),
            }
        )

    frame = pd.DataFrame(rows)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    summary = frame.groupby("event_type", dropna=False).size().reset_index(name="count")
    timeline = px.scatter(
        frame,
        x="ts",
        y="event_type",
        color="symbol",
        title="Run Events Timeline",
        hover_data=["value"],
    )
    bars = px.bar(summary, x="event_type", y="count", title="Run Event Counts")
    html_parts = [
        "<html><head><meta charset='utf-8'><title>algotrade run report</title></head><body>",
        timeline.to_html(full_html=False, include_plotlyjs="cdn"),
        bars.to_html(full_html=False, include_plotlyjs=False),
        "</body></html>",
    ]
    output.write_text("".join(html_parts), encoding="utf-8")

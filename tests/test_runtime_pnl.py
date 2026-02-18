from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from algotrade import runtime
from algotrade.config import Settings
from algotrade.domain.models import PortfolioSnapshot


@dataclass
class StubBroker:
    equity: float

    def get_portfolio(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            cash=self.equity,
            equity=self.equity,
            buying_power=self.equity,
            positions={},
        )


class StubStateStore:
    def __init__(self) -> None:
        self.closed = False

    def record_run(self, run_id: str, mode: str, strategy_id: str, symbols: list[str]) -> None:
        _ = (run_id, mode, strategy_id, symbols)

    def close(self) -> None:
        self.closed = True


class StubEventSink:
    def __init__(self, path: str) -> None:
        self.path = path
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


class StubLogger:
    def __init__(self) -> None:
        self.pnl_calls: list[tuple[float, float, float, float | None]] = []

    def run_started(
        self,
        run_id: str,
        mode: str,
        strategy_id: str,
        symbols: list[str],
    ) -> None:
        _ = (run_id, mode, strategy_id, symbols)

    def run_pnl(
        self,
        equity: float,
        pnl: float,
        pnl_pct: float,
        start_equity: float | None = None,
    ) -> None:
        self.pnl_calls.append((equity, pnl, pnl_pct, start_equity))

    def error(self, message: str) -> None:
        _ = message


def _patch_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    broker: StubBroker,
    state_store: StubStateStore,
    logger_instances: list[StubLogger],
) -> None:
    monkeypatch.setattr(
        runtime,
        "create_strategy",
        lambda _strategy_id, _settings: SimpleNamespace(strategy_id="scalping"),
    )
    monkeypatch.setattr(runtime, "build_data_provider", lambda _settings, _strategy: object())
    monkeypatch.setattr(runtime, "build_broker", lambda _settings: broker)
    monkeypatch.setattr(runtime, "build_state_store", lambda _settings: state_store)
    monkeypatch.setattr(runtime, "JsonlEventSink", StubEventSink)
    monkeypatch.setattr(runtime, "generate_plotly_report", lambda _events, _report: None)
    monkeypatch.setattr(
        runtime,
        "HumanLogger",
        lambda level="INFO": logger_instances.append(StubLogger()) or logger_instances[-1],
    )
    monkeypatch.setattr(runtime, "reconcile_state", lambda **_kwargs: None)


def test_run_logs_pnl_when_cycle_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    broker = StubBroker(equity=1050.0)
    state_store = StubStateStore()
    logger_instances: list[StubLogger] = []
    _patch_runtime_dependencies(
        monkeypatch,
        broker=broker,
        state_store=state_store,
        logger_instances=logger_instances,
    )

    def fake_execute_cycle(*, run_metrics: dict[str, float | None], **_kwargs) -> None:
        run_metrics["start_equity"] = 1000.0

    monkeypatch.setattr(runtime, "execute_cycle", fake_execute_cycle)

    exit_code = runtime.run(
        Settings(
            mode="live",
            strategy="scalping",
            symbols=["BTCUSD"],
            cycles=2,
            events_dir=str(tmp_path),
        )
    )

    assert exit_code == 0
    assert len(logger_instances) == 1
    assert logger_instances[0].pnl_calls == [(1050.0, 50.0, 0.05, 1000.0)]
    assert state_store.closed is True


def test_run_logs_pnl_after_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    broker = StubBroker(equity=1020.0)
    state_store = StubStateStore()
    logger_instances: list[StubLogger] = []
    _patch_runtime_dependencies(
        monkeypatch,
        broker=broker,
        state_store=state_store,
        logger_instances=logger_instances,
    )

    def fake_execute_cycle(*, run_metrics: dict[str, float | None], **_kwargs) -> None:
        run_metrics["start_equity"] = 1000.0
        raise KeyboardInterrupt

    monkeypatch.setattr(runtime, "execute_cycle", fake_execute_cycle)

    exit_code = runtime.run(
        Settings(
            mode="live",
            strategy="scalping",
            symbols=["BTCUSD"],
            cycles=None,
            events_dir=str(tmp_path),
        )
    )

    assert exit_code == 0
    assert len(logger_instances) == 1
    assert logger_instances[0].pnl_calls == [(1020.0, 20.0, 0.02, 1000.0)]
    assert state_store.closed is True

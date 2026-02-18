from __future__ import annotations

import pytest

from algotrade.config import Settings
from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.runtime import show_portfolio


class StubPortfolioBroker:
    def __init__(self) -> None:
        self.positions_calls = 0
        self.portfolio_calls = 0

    def get_positions(self) -> dict[str, Position]:
        self.positions_calls += 1
        return {"AAPL": Position(symbol="AAPL", qty=2), "TSLA": Position(symbol="TSLA", qty=-1)}

    def get_portfolio(self) -> PortfolioSnapshot:
        self.portfolio_calls += 1
        return PortfolioSnapshot(
            cash=2500.0,
            equity=3250.0,
            buying_power=3000.0,
            positions={},
        )


def test_show_portfolio_requires_live_mode() -> None:
    with pytest.raises(ValueError, match="--portfolio requires --mode live"):
        show_portfolio(Settings(mode="backtest"))


def test_show_portfolio_reads_broker_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    broker = StubPortfolioBroker()
    monkeypatch.setattr("algotrade.runtime.build_broker", lambda _settings: broker)

    exit_code = show_portfolio(Settings(mode="live"))

    assert exit_code == 0
    assert broker.positions_calls == 1
    assert broker.portfolio_calls == 1


class StubPortfolioDetailsBroker(StubPortfolioBroker):
    def __init__(self) -> None:
        super().__init__()
        self.details_calls = 0

    def get_positions_details(self) -> list[dict[str, float | str]]:
        self.details_calls += 1
        return [
            {
                "symbol": "BTCUSD",
                "qty": 0.997499995,
                "market_value": 68000.0,
                "cost_basis": 65000.0,
                "unrealized_pl": 3000.0,
            }
        ]

    def get_positions(self) -> dict[str, Position]:
        self.positions_calls += 1
        return {"BTCUSD": Position(symbol="BTCUSD", qty=1)}


def test_show_portfolio_reads_detailed_positions_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = StubPortfolioDetailsBroker()
    monkeypatch.setattr("algotrade.runtime.build_broker", lambda _settings: broker)

    exit_code = show_portfolio(Settings(mode="live"))

    assert exit_code == 0
    assert broker.positions_calls == 1
    assert broker.portfolio_calls == 1
    assert broker.details_calls == 1

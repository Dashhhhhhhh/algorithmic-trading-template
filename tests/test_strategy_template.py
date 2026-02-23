from __future__ import annotations

import pandas as pd

from algotrade.domain.models import PortfolioSnapshot, Position
from algotrade.strategy_core.algorithm_imports import (
    QCAlgorithm,
    QCAlgorithmStrategyAdapter,
    Resolution,
    timedelta,
)


class DonchianChannelBreakoutAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(self.end_date - timedelta(5 * 365))
        self.set_cash(100_000)
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY", Resolution.DAILY)
        self._dch = self.dch(self._equity, 3, 3)
        self._can_short = False

    def on_data(self, data):
        if not data.bars:
            return
        if (
            self._equity.price > self._dch.upper_band.previous.value
            and not self._equity.holdings.is_long
        ):
            self.set_holdings(self._equity, 1)
        elif self._equity.price < self._dch.lower_band.previous.value:
            if self._can_short and not self._equity.holdings.is_short:
                self.set_holdings(self._equity, -1)
            if not self._can_short and self._equity.holdings.is_long:
                self.set_holdings(self._equity, 0)
        self.plot("Custom", "Donchian Channel High", self._dch.upper_band.previous.value)
        self.plot("Custom", "Close Price", self._equity.price)
        self.plot("Custom", "Donchian Channel Low", self._dch.lower_band.previous.value)


class HoldOnceAlgorithm(QCAlgorithm):
    def initialize(self):
        self._equity = self.add_equity("SPY", Resolution.DAILY)
        self._did_set = False

    def on_data(self, data):
        if not data.bars or self._did_set:
            return
        self.set_holdings(self._equity, 1)
        self._did_set = True


def _snapshot(positions: dict[str, Position] | None = None) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        cash=1000.0,
        equity=1000.0,
        buying_power=1000.0,
        positions=positions or {},
    )


def test_pasted_qcalgorithm_longs_on_upper_breakout() -> None:
    adapter = QCAlgorithmStrategyAdapter(
        algorithm_type=DonchianChannelBreakoutAlgorithm,
        strategy_id="template",
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 100.5, 102.0, 102.5],
            "high": [101.0, 102.0, 101.5, 103.0, 104.0],
            "low": [99.0, 100.0, 99.5, 101.0, 102.0],
            "close": [100.5, 101.5, 101.0, 103.0, 103.5],
        }
    )

    targets = adapter.decide_targets({"SPY": bars}, _snapshot())

    assert targets["SPY"] == 1.0


def test_pasted_qcalgorithm_exposes_declared_symbols() -> None:
    adapter = QCAlgorithmStrategyAdapter(
        algorithm_type=DonchianChannelBreakoutAlgorithm,
        strategy_id="template",
    )

    assert adapter.declared_symbols() == ["SPY"]


def test_pasted_qcalgorithm_flattens_when_shorting_disabled() -> None:
    adapter = QCAlgorithmStrategyAdapter(
        algorithm_type=DonchianChannelBreakoutAlgorithm,
        strategy_id="template",
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 100.5, 99.0, 98.5],
            "high": [101.0, 102.0, 101.5, 99.5, 99.0],
            "low": [99.0, 100.0, 99.5, 98.0, 97.5],
            "close": [100.5, 101.0, 100.0, 98.0, 97.5],
        }
    )
    snapshot = _snapshot({"SPY": Position(symbol="SPY", qty=1.0)})

    targets = adapter.decide_targets({"SPY": bars}, snapshot)

    assert targets["SPY"] == 0.0


def test_pasted_qcalgorithm_persists_target_until_changed() -> None:
    adapter = QCAlgorithmStrategyAdapter(
        algorithm_type=HoldOnceAlgorithm,
        strategy_id="hold_once",
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
        }
    )

    first_targets = adapter.decide_targets({"SPY": bars}, _snapshot())
    second_targets = adapter.decide_targets(
        {"SPY": bars},
        _snapshot({"SPY": Position(symbol="SPY", qty=0.5)}),
    )

    assert first_targets["SPY"] == 1.0
    assert second_targets["SPY"] == 1.0

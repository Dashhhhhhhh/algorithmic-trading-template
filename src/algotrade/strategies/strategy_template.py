"""Copy-and-edit template for pasted QCAlgorithm strategies.

How to use:
1. Copy this file to a new module in ``src/algotrade/strategies/``.
2. Paste your strategy class in Lean format (``class X(QCAlgorithm)``).
3. Run with ``--strategy <new_module_name>``.

The registry will auto-wrap the QCAlgorithm class; no Strategy subclass is required.
"""
# ruff: noqa: F403,F405,I001

# region imports
from AlgorithmImports import *
# endregion


class TemplateAlgorithm(QCAlgorithm):
    """Replace this class with your pasted QCAlgorithm strategy."""

    def initialize(self):
        self.set_start_date(self.end_date - timedelta(days=365))
        self.set_cash(100_000)
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY", Resolution.DAILY)
        self._can_short = False

    def on_data(self, data):
        if not data.bars:
            return

        # Paste your own rule logic here.
        if self._equity.price > 0 and not self._equity.holdings.is_long:
            self.set_holdings(self._equity, 1)
        elif self._equity.holdings.is_long:
            self.set_holdings(self._equity, 0)

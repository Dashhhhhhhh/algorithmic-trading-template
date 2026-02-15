"""Execution workflow: data -> signal -> order decision -> broker action."""

from __future__ import annotations

import logging

from app.broker.alpaca import AlpacaClient
from app.broker.models import OrderRequest, OrderSide, Position
from app.data.alpha_vantage import AlphaVantageClient
from app.strategy.base import Signal, Strategy
from app.utils.errors import BrokerError, DataProviderError, StrategyError


class Trader:
    """Coordinates market data, strategy evaluation, and order execution."""

    def __init__(
        self,
        data_client: AlphaVantageClient,
        broker_client: AlpacaClient,
        strategy: Strategy,
        dry_run: bool = True,
        default_qty: int = 1,
    ) -> None:
        self.data_client = data_client
        self.broker_client = broker_client
        self.strategy = strategy
        self.dry_run = dry_run
        self.default_qty = default_qty
        self.logger = logging.getLogger("algotrade.execution.trader")

    def run_once(self, symbols: list[str], qty: int | None = None) -> None:
        """Execute one full trading cycle for provided symbols."""
        order_qty = qty or self.default_qty

        account = self.broker_client.get_account()
        positions = self.broker_client.get_positions()
        self.logger.info(
            "Account status=%s cash=%.2f buying_power=%.2f trading_blocked=%s",
            account.status,
            account.cash,
            account.buying_power,
            account.trading_blocked,
        )

        if account.trading_blocked:
            self.logger.warning("Trading is blocked on this account. Exiting cycle.")
            return

        for symbol in symbols:
            normalized_symbol = symbol.upper()
            try:
                self._handle_symbol(
                    symbol=normalized_symbol,
                    positions=positions,
                    qty=order_qty,
                )
            except (DataProviderError, StrategyError, BrokerError) as exc:
                self.logger.error("%s: %s", normalized_symbol, exc)
            except Exception as exc:  # pragma: no cover - safety net
                self.logger.exception("%s: unexpected error: %s", normalized_symbol, exc)

    def _handle_symbol(
        self,
        symbol: str,
        positions: dict[str, Position],
        qty: int,
    ) -> None:
        bars = self.data_client.fetch_daily(symbol=symbol)
        signal = self.strategy.generate_signal(symbol=symbol, bars=bars)

        position = positions.get(symbol)
        current_qty = float(position.qty) if position is not None else 0.0

        self.logger.info("%s: signal=%s current_position=%.4f", symbol, signal.value, current_qty)

        order = self._build_order(symbol=symbol, signal=signal, current_qty=current_qty, qty=qty)
        if order is None:
            self.logger.info("%s: no order needed.", symbol)
            return

        if self.dry_run:
            self.logger.info(
                "DRY RUN | %s %s x%s (order not sent)",
                order.side.value.upper(),
                order.symbol,
                order.qty,
            )
            return

        response = self.broker_client.submit_market_order(order)
        self.logger.info(
            "Order submitted | id=%s symbol=%s side=%s qty=%s status=%s",
            response.get("id"),
            response.get("symbol"),
            response.get("side"),
            response.get("qty"),
            response.get("status"),
        )

    @staticmethod
    def _build_order(symbol: str, signal: Signal, current_qty: float, qty: int) -> OrderRequest | None:
        """Translate signal and position state into an order, if any."""
        if signal == Signal.BUY and current_qty <= 0:
            return OrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY)

        if signal == Signal.SELL and current_qty > 0:
            sell_qty = max(1, min(qty, int(current_qty)))
            return OrderRequest(symbol=symbol, qty=sell_qty, side=OrderSide.SELL)

        return None

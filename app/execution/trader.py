"""Execution workflow: data -> signal -> order decision -> broker action."""

from __future__ import annotations

import logging
import sys
import time

from app.broker.alpaca import AlpacaClient
from app.broker.models import AccountInfo, MarketClock, OrderRequest, OrderSide, Position
from app.data.base import MarketDataClient
from app.strategy.base import Signal, Strategy
from app.utils.errors import BrokerError, DataProviderError, StrategyError


class Trader:
    """Coordinates market data, strategy evaluation, and order execution."""

    def __init__(
        self,
        data_client: MarketDataClient,
        broker_client: AlpacaClient,
        strategy: Strategy,
        dry_run: bool = True,
        default_qty: int = 1,
        allow_short: bool = True,
    ) -> None:
        self.data_client = data_client
        self.broker_client = broker_client
        self.strategy = strategy
        self.dry_run = dry_run
        self.default_qty = default_qty
        self.allow_short = allow_short
        self.logger = logging.getLogger("algotrade.execution.trader")

    def run_once(self, symbols: list[str], qty: int | None = None) -> None:
        """Execute one full trading cycle for provided symbols."""
        order_qty = qty or self.default_qty

        account = self.broker_client.get_account()
        clock = self.broker_client.get_clock()
        positions = self.broker_client.get_positions()
        day_pnl_text = self._format_day_pnl(account)
        self.logger.info(
            "Account status=%s cash=%.2f buying_power=%.2f day_pnl=%s trading_blocked=%s",
            account.status,
            account.cash,
            account.buying_power,
            day_pnl_text,
            account.trading_blocked,
        )
        self._log_market_clock(clock)

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
        reference_price = float(bars["close"].iloc[-1])
        signal = self.strategy.generate_signal(symbol=symbol, bars=bars)

        position = positions.get(symbol)
        current_qty = self._signed_position_qty(position)

        self.logger.info(
            "%s: signal=%s current_position=%s ref_price=%.2f",
            symbol,
            signal.value,
            current_qty,
            reference_price,
        )

        order = self._build_order(
            symbol=symbol,
            signal=signal,
            current_qty=current_qty,
            qty=qty,
            allow_short=self.allow_short,
        )
        if order is None:
            self.logger.info("%s: no order needed.", symbol)
            return

        if self.dry_run:
            est_notional = reference_price * float(order.qty)
            self.logger.info(
                "DRY RUN | %s %s x%s est_notional=$%.2f (order not sent)",
                order.side.value.upper(),
                order.symbol,
                order.qty,
                est_notional,
            )
            return

        if not self._prepare_open_orders_for_symbol(symbol=symbol, desired_side=order.side):
            return

        response = self.broker_client.submit_market_order(order)
        self._log_order_response(response=response, fallback_ref_price=reference_price)

        # Quick follow-up for market-open sessions to capture fill amount fast.
        order_id = str(response.get("id", ""))
        order_status = str(response.get("status", ""))
        if order_id and order_status in {"accepted", "new", "pending_new"}:
            time.sleep(0.8)
            refreshed = self.broker_client.get_order(order_id=order_id)
            self._log_order_response(response=refreshed, fallback_ref_price=reference_price, prefix="Order update")

    @staticmethod
    def _signed_position_qty(position: Position | None) -> int:
        """Convert Alpaca position into signed whole-share quantity.

        Positive = long, negative = short, zero = flat.
        """
        if position is None:
            return 0

        qty_abs = int(round(abs(position.qty)))
        side = position.side.strip().lower()
        if side == "short":
            return -qty_abs
        return qty_abs

    @staticmethod
    def _build_order(
        symbol: str,
        signal: Signal,
        current_qty: int,
        qty: int,
        allow_short: bool,
    ) -> OrderRequest | None:
        """Translate signal into a target position and submit delta order.

        BUY  -> target +qty
        SELL -> target -qty (or 0 when shorting disabled)
        HOLD -> no change
        """
        if signal == Signal.HOLD:
            return None

        if signal == Signal.BUY:
            target_qty = qty
        elif signal == Signal.SELL:
            target_qty = -qty if allow_short else 0
        else:
            return None

        delta = target_qty - current_qty
        if delta == 0:
            return None

        if delta > 0:
            return OrderRequest(symbol=symbol, qty=delta, side=OrderSide.BUY)
        return OrderRequest(symbol=symbol, qty=abs(delta), side=OrderSide.SELL)

    def _prepare_open_orders_for_symbol(self, symbol: str, desired_side: OrderSide) -> bool:
        """Refresh any open order for the symbol before submitting a new one.

        This keeps order flow active instead of idling behind a pending order.
        """
        open_orders = self.broker_client.get_open_orders(symbol=symbol)
        symbol_orders = [
            order
            for order in open_orders
            if str(order.get("symbol", "")).upper() == symbol.upper()
        ]
        if not symbol_orders:
            return True

        for order in symbol_orders:
            order_id = str(order.get("id", ""))
            side = str(order.get("side", "")).lower()
            if not order_id:
                continue

            self.broker_client.cancel_order(order_id=order_id)
            self.logger.info("%s: canceled open order id=%s side=%s", symbol, order_id, side)

        return True

    @staticmethod
    def _to_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _log_order_response(
        self,
        response: dict,
        fallback_ref_price: float,
        prefix: str = "Order submitted",
    ) -> None:
        symbol = str(response.get("symbol", ""))
        side = str(response.get("side", ""))
        qty = self._to_float(response.get("qty"), default=0.0)
        status = str(response.get("status", ""))
        order_id = str(response.get("id", ""))

        filled_qty = self._to_float(response.get("filled_qty"), default=0.0)
        filled_avg_price = self._to_float(response.get("filled_avg_price"), default=0.0)
        est_notional = qty * fallback_ref_price
        filled_notional = filled_qty * filled_avg_price if filled_avg_price > 0 else 0.0

        self.logger.info(
            "%s | id=%s symbol=%s side=%s qty=%.4f status=%s est_notional=$%.2f filled_qty=%.4f filled_avg=$%.2f filled_notional=$%.2f",
            prefix,
            order_id,
            symbol,
            side,
            qty,
            status,
            est_notional,
            filled_qty,
            filled_avg_price,
            filled_notional,
        )

    def _log_market_clock(self, clock: MarketClock) -> None:
        state = "OPEN" if clock.is_open else "CLOSED"
        self.logger.info(
            "Market=%s timestamp=%s next_open=%s next_close=%s",
            state,
            clock.timestamp,
            clock.next_open,
            clock.next_close,
        )

    @staticmethod
    def _format_day_pnl(account: AccountInfo) -> str:
        """Format day P/L with terminal color: green positive, red negative."""
        if account.last_equity <= 0:
            return "n/a"

        pnl = account.equity - account.last_equity
        pnl_pct = (pnl / account.last_equity) * 100
        pnl_text = f"${pnl:+,.2f} ({pnl_pct:+.2f}%)"

        if not sys.stderr.isatty():
            return pnl_text

        reset = "\033[0m"
        if pnl > 0:
            return f"\033[32m{pnl_text}{reset}"
        if pnl < 0:
            return f"\033[31m{pnl_text}{reset}"
        return pnl_text

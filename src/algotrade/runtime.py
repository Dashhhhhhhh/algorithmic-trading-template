"""Runtime wiring and trading loop orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import sleep
from typing import Any
from uuid import uuid4

from algotrade.brokers.alpaca_paper import AlpacaPaperBroker
from algotrade.brokers.backtest_broker import BacktestBroker
from algotrade.brokers.base import Broker
from algotrade.config import Settings
from algotrade.data.alpaca_market_data import AlpacaMarketDataProvider
from algotrade.data.base import MarketDataProvider
from algotrade.data.csv_data import CsvDataProvider
from algotrade.domain.events import TradeEvent
from algotrade.domain.models import OrderRequest, OrderSide, Position, RiskLimits
from algotrade.execution.engine import apply_risk_gates, compute_orders
from algotrade.logging.event_sink import JsonlEventSink, generate_plotly_report
from algotrade.logging.logger import HumanLogger
from algotrade.state.sqlite_store import SqliteStateStore
from algotrade.state.store import OrderIntentRecord, StateStore
from algotrade.strategies.base import Strategy
from algotrade.strategies.registry import create_strategy


class NoopStateStore:
    """No-op state store for backtest mode."""

    def record_run(self, run_id: str, mode: str, strategy_id: str, symbols: list[str]) -> None:
        _ = (run_id, mode, strategy_id, symbols)

    def save_intended_order(self, run_id: str, request: OrderRequest) -> None:
        _ = (run_id, request)

    def mark_submitted(self, client_order_id: str, broker_order_id: str, status: str) -> None:
        _ = (client_order_id, broker_order_id, status)

    def mark_reconciled(self, client_order_id: str, status: str) -> None:
        _ = (client_order_id, status)

    def list_active_intents(self) -> list[OrderIntentRecord]:
        return []

    def has_active_intent(self, symbol: str, side: str, qty: int) -> bool:
        _ = (symbol, side, qty)
        return False

    def close(self) -> None:
        return None


def run(settings: Settings) -> int:
    """Run algorithmic trading in once or continuous mode."""
    strategy = create_strategy(settings.strategy, settings)
    data_provider = build_data_provider(settings)
    broker = build_broker(settings)
    state_store: StateStore = build_state_store(settings)

    run_id = uuid4().hex
    run_directory = Path(settings.events_dir) / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    events_path = run_directory / "events.jsonl"
    report_path = run_directory / "report.html"

    event_sink = JsonlEventSink(str(events_path))
    human_logger = HumanLogger(level=settings.log_level)

    state_store.record_run(run_id, settings.mode, strategy.strategy_id, settings.symbols)
    human_logger.run_started(run_id, settings.mode, strategy.strategy_id, settings.symbols)
    event_sink.emit(
        TradeEvent(
            run_id=run_id,
            mode=settings.mode,
            strategy_id=strategy.strategy_id,
            event_type="run_started",
            payload={"symbols": settings.symbols},
        )
    )

    if settings.mode in {"paper", "live"}:
        reconcile_state(
            state_store=state_store,
            broker=broker,
            event_sink=event_sink,
            human_logger=human_logger,
            run_id=run_id,
            settings=settings,
        )

    exit_code = 0
    try:
        if settings.should_run_continuously():
            while True:
                execute_cycle(
                    settings=settings,
                    strategy=strategy,
                    data_provider=data_provider,
                    broker=broker,
                    state_store=state_store,
                    run_id=run_id,
                    event_sink=event_sink,
                    human_logger=human_logger,
                )
                sleep(float(settings.interval_seconds))
        else:
            execute_cycle(
                settings=settings,
                strategy=strategy,
                data_provider=data_provider,
                broker=broker,
                state_store=state_store,
                run_id=run_id,
                event_sink=event_sink,
                human_logger=human_logger,
            )
    except KeyboardInterrupt:
        exit_code = 0
    except Exception as exc:
        human_logger.error(str(exc))
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="error",
                payload={"message": str(exc)},
            )
        )
        exit_code = 1
    finally:
        try:
            generate_plotly_report(str(events_path), str(report_path))
        finally:
            state_store.close()

    return exit_code


def execute_cycle(
    settings: Settings,
    strategy: Strategy,
    data_provider: MarketDataProvider,
    broker: Broker,
    state_store: StateStore,
    run_id: str,
    event_sink: JsonlEventSink,
    human_logger: HumanLogger,
) -> None:
    """Run one decision and submission cycle."""
    portfolio = broker.get_portfolio()
    positions = broker.get_positions()
    bars_by_symbol = build_bars_by_symbol(settings.symbols, data_provider)
    targets = strategy.decide_targets(bars_by_symbol, portfolio)
    decision_details: dict[str, dict[str, Any]] = {}

    for symbol, target in sorted(targets.items()):
        current_qty = positions.get(symbol, Position(symbol=symbol, qty=0)).qty
        payload: dict[str, Any] = {
            "symbol": symbol,
            "target_qty": target,
            "current_qty": current_qty,
        }
        if settings.mode == "backtest":
            details = summarize_backtest_decision(
                bars=bars_by_symbol.get(symbol),
                lookback_bars=settings.momentum_lookback_bars,
                target_qty=target,
                current_qty=current_qty,
            )
            decision_details[symbol] = details
            human_logger.decision(symbol, target, current_qty, details=details)
            payload.update(details)
        else:
            human_logger.decision(symbol, target, current_qty)
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="decision",
                payload=payload,
            )
        )

    raw_orders = compute_orders(
        current_positions=positions,
        targets=targets,
        default_order_type=settings.default_order_type,
    )
    risk_limits = RiskLimits(
        max_abs_position_per_symbol=settings.max_abs_position_per_symbol,
        allow_short=settings.allow_short,
    )
    orders = apply_risk_gates(raw_orders, portfolio, risk_limits)

    prepared_orders = prepare_orders(
        orders=orders,
        run_id=run_id,
        state_store=state_store,
        event_sink=event_sink,
        human_logger=human_logger,
        settings=settings,
        strategy=strategy,
    )
    if settings.mode == "backtest":
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="cycle_summary",
                payload={
                    "stage": "pre_submit",
                    "portfolio": serialize_portfolio(portfolio),
                    "positions": serialize_positions(positions),
                    "targets": dict(sorted(targets.items())),
                    "decisions": decision_details,
                    "raw_orders": serialize_orders(raw_orders),
                    "risk_orders": serialize_orders(orders),
                    "prepared_orders": serialize_orders(prepared_orders),
                    "duplicate_blocked_count": max(0, len(orders) - len(prepared_orders)),
                },
            )
        )

    if not prepared_orders:
        if settings.mode == "backtest":
            event_sink.emit(
                TradeEvent(
                    run_id=run_id,
                    mode=settings.mode,
                    strategy_id=strategy.strategy_id,
                    event_type="cycle_summary",
                    payload={
                        "stage": "post_submit",
                        "submitted_order_count": 0,
                        "positions_after": serialize_positions(broker.get_positions()),
                        "portfolio_after": serialize_portfolio(broker.get_portfolio()),
                    },
                )
            )
        return

    receipts = broker.submit_orders(prepared_orders)
    for receipt in receipts:
        if receipt.client_order_id:
            state_store.mark_submitted(
                client_order_id=receipt.client_order_id,
                broker_order_id=receipt.order_id,
                status=receipt.status,
            )
        human_logger.order_update(receipt.order_id, receipt.status, receipt.client_order_id)
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="order_update",
                payload={
                    "order_id": receipt.order_id,
                    "client_order_id": receipt.client_order_id,
                    "symbol": receipt.symbol,
                    "side": receipt.side.value,
                    "qty": receipt.qty,
                    "status": receipt.status,
                },
            )
        )
    if settings.mode == "backtest":
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="cycle_summary",
                payload={
                    "stage": "post_submit",
                    "submitted_order_count": len(receipts),
                    "receipts": serialize_receipts(receipts),
                    "positions_after": serialize_positions(broker.get_positions()),
                    "portfolio_after": serialize_portfolio(broker.get_portfolio()),
                },
            )
        )


def prepare_orders(
    orders: list[OrderRequest],
    run_id: str,
    state_store: StateStore,
    event_sink: JsonlEventSink,
    human_logger: HumanLogger,
    settings: Settings,
    strategy: Strategy,
) -> list[OrderRequest]:
    """Attach client ids and persist intent before submission."""
    prepared: list[OrderRequest] = []
    for index, order in enumerate(orders):
        if state_store.has_active_intent(order.symbol, order.side.value, order.qty):
            event_sink.emit(
                TradeEvent(
                    run_id=run_id,
                    mode=settings.mode,
                    strategy_id=strategy.strategy_id,
                    event_type="order_update",
                    payload={
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "qty": order.qty,
                        "status": "duplicate_blocked",
                    },
                )
            )
            continue
        client_order_id = build_client_order_id(run_id, index, order.symbol)
        order_with_id = replace(order, client_order_id=client_order_id)
        state_store.save_intended_order(run_id, order_with_id)
        human_logger.order_submit(order.symbol, order.side.value, order.qty, client_order_id)
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="order_submit",
                payload={
                    "symbol": order_with_id.symbol,
                    "side": order_with_id.side.value,
                    "qty": order_with_id.qty,
                    "client_order_id": order_with_id.client_order_id,
                },
            )
        )
        prepared.append(order_with_id)
    return prepared


def build_client_order_id(run_id: str, index: int, symbol: str) -> str:
    """Generate stable client order id format."""
    return f"{run_id[:10]}-{symbol.upper()}-{index}"


def summarize_backtest_decision(
    bars: Any,
    lookback_bars: int,
    target_qty: int,
    current_qty: int,
) -> dict[str, Any]:
    """Build per-symbol diagnostics used in backtest analysis."""
    details: dict[str, Any] = {
        "delta_qty": target_qty - current_qty,
    }
    if bars is None:
        return details
    try:
        bar_count = int(len(bars))
    except TypeError:
        return details
    details["bars"] = bar_count
    if bar_count <= 0 or not hasattr(bars, "columns"):
        return details
    if "close" not in bars.columns:
        return details

    close = bars["close"]
    latest_close = float(close.iloc[-1])
    details["close"] = round(latest_close, 6)

    index = getattr(bars, "index", None)
    if index is not None and len(index) > 0:
        last_index = index[-1]
        details["asof"] = (
            last_index.isoformat() if hasattr(last_index, "isoformat") else str(last_index)
        )

    if "volume" in bars.columns:
        details["volume"] = float(bars["volume"].iloc[-1])

    if bar_count > 1:
        previous_close = float(close.iloc[-2])
        if previous_close != 0:
            details["ret_1"] = round((latest_close - previous_close) / previous_close, 6)

    if lookback_bars > 0 and bar_count > lookback_bars:
        reference_close = float(close.iloc[-1 - lookback_bars])
        if reference_close != 0:
            details["ret_lb"] = round((latest_close - reference_close) / reference_close, 6)

    return details


def serialize_positions(positions: dict[str, Position]) -> dict[str, int]:
    """Convert position objects into a deterministic, JSON-friendly mapping."""
    return {symbol: position.qty for symbol, position in sorted(positions.items())}


def serialize_portfolio(portfolio: Any) -> dict[str, Any]:
    """Convert a portfolio snapshot into a stable event payload."""
    return {
        "cash": round(float(portfolio.cash), 4),
        "equity": round(float(portfolio.equity), 4),
        "buying_power": round(float(portfolio.buying_power), 4),
        "positions": serialize_positions(getattr(portfolio, "positions", {})),
    }


def serialize_orders(orders: list[OrderRequest]) -> list[dict[str, Any]]:
    """Convert order requests into structured event payloads."""
    return [
        {
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": order.qty,
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "client_order_id": order.client_order_id,
        }
        for order in orders
    ]


def serialize_receipts(receipts: list[Any]) -> list[dict[str, Any]]:
    """Convert broker receipts into structured event payloads."""
    return [
        {
            "order_id": receipt.order_id,
            "symbol": receipt.symbol,
            "side": receipt.side.value,
            "qty": receipt.qty,
            "status": receipt.status,
            "client_order_id": receipt.client_order_id,
            "raw": receipt.raw,
        }
        for receipt in receipts
    ]


def build_bars_by_symbol(symbols: list[str], data_provider: MarketDataProvider) -> dict[str, Any]:
    """Fetch bar data for all symbols."""
    bars_by_symbol: dict[str, Any] = {}
    for symbol in symbols:
        bars_by_symbol[symbol] = data_provider.get_bars(symbol)
    return bars_by_symbol


def reconcile_state(
    state_store: StateStore,
    broker: Broker,
    event_sink: JsonlEventSink,
    human_logger: HumanLogger,
    run_id: str,
    settings: Settings,
) -> None:
    """Reconcile unresolved intents on startup and avoid duplicate submissions."""
    active_intents = state_store.list_active_intents()
    if not active_intents:
        return

    open_orders = broker.get_open_orders()
    open_client_ids = {order.client_order_id for order in open_orders if order.client_order_id}
    positions = broker.get_positions()

    for intent in active_intents:
        status = resolve_intent_status(intent, open_client_ids, positions)
        state_store.mark_reconciled(intent.client_order_id, status)
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=settings.strategy,
                event_type="order_update",
                payload={
                    "client_order_id": intent.client_order_id,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "qty": intent.qty,
                    "status": status,
                },
            )
        )
        human_logger.order_update(
            order_id="reconcile",
            status=status,
            client_order_id=intent.client_order_id,
        )


def resolve_intent_status(
    intent: OrderIntentRecord,
    open_client_ids: set[str],
    positions: dict[str, Position],
) -> str:
    """Determine reconciled status for a persisted intent."""
    if intent.client_order_id in open_client_ids:
        return "submitted"
    position_qty = positions.get(intent.symbol, Position(symbol=intent.symbol, qty=0)).qty
    if intent.side == OrderSide.BUY.value and position_qty >= intent.qty:
        return "filled_reconciled"
    if intent.side == OrderSide.SELL.value and position_qty <= -intent.qty:
        return "filled_reconciled"
    return "submitted"


def build_broker(settings: Settings) -> Broker:
    """Select broker implementation based on mode."""
    if settings.mode == "backtest":
        return BacktestBroker(starting_cash=settings.backtest_starting_cash)
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required for paper/live modes")
    return AlpacaPaperBroker(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        base_url=settings.alpaca_base_url,
    )


def build_data_provider(settings: Settings) -> MarketDataProvider:
    """Select data provider from mode and data source."""
    source = settings.effective_data_source()
    if source == "csv":
        return CsvDataProvider(data_dir=settings.historical_data_dir)
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required for Alpaca data")
    return AlpacaMarketDataProvider(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        data_base_url=settings.alpaca_data_url,
        timeframe=settings.timeframe,
    )


def build_state_store(settings: Settings) -> StateStore:
    """Select state store implementation from mode."""
    if settings.mode == "backtest":
        return NoopStateStore()
    return SqliteStateStore(settings.state_db_path)

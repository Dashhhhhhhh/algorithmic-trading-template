"""Runtime wiring and trading loop orchestration."""

from __future__ import annotations

from collections import Counter
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

    if settings.mode == "live":
        reconcile_state(
            state_store=state_store,
            broker=broker,
            event_sink=event_sink,
            human_logger=human_logger,
            run_id=run_id,
            settings=settings,
        )

    run_metrics: dict[str, float | None] = {
        "start_equity": None,
        "previous_equity": None,
    }

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
                    run_metrics=run_metrics,
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
                run_metrics=run_metrics,
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
    run_metrics: dict[str, float | None] | None = None,
) -> None:
    """Run one decision and submission cycle."""
    if run_metrics is None:
        run_metrics = {
            "start_equity": None,
            "previous_equity": None,
        }

    if settings.mode == "live":
        reconcile_state(
            state_store=state_store,
            broker=broker,
            event_sink=event_sink,
            human_logger=human_logger,
            run_id=run_id,
            settings=settings,
        )

    positions = broker.get_positions()
    bars_by_symbol = build_bars_by_symbol(settings.symbols, data_provider)
    latest_prices = build_latest_prices(bars_by_symbol)
    if settings.mode == "backtest" and isinstance(broker, BacktestBroker):
        broker.update_market_prices(latest_prices)
    portfolio = broker.get_portfolio()
    positions = broker.get_positions()
    pnl_metrics = compute_equity_metrics(run_metrics, float(portfolio.equity))
    targets = strategy.decide_targets(bars_by_symbol, portfolio)
    decision_details: dict[str, dict[str, Any]] = {}
    include_details = settings.mode == "backtest" or strategy.strategy_id == "scalping"
    lookback_bars = (
        settings.scalping_lookback_bars
        if strategy.strategy_id == "scalping"
        else settings.momentum_lookback_bars
    )

    for symbol, target in sorted(targets.items()):
        current_qty = positions.get(symbol, Position(symbol=symbol, qty=0)).qty
        payload: dict[str, Any] = {
            "symbol": symbol,
            "target_qty": target,
            "current_qty": current_qty,
        }
        if include_details:
            details = summarize_decision_details(
                bars=bars_by_symbol.get(symbol),
                lookback_bars=lookback_bars,
                target_qty=target,
                current_qty=current_qty,
            )
            if strategy.strategy_id == "scalping":
                details["scalping_threshold"] = settings.scalping_threshold
                details["scalping_flip_seconds"] = settings.scalping_flip_seconds
                details["scalping_allow_short"] = settings.scalping_allow_short
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
    risk_blocked = find_risk_blocked_orders(raw_orders, orders, portfolio, risk_limits)

    for blocked in risk_blocked:
        blocked_payload = {
            "symbol": blocked["symbol"],
            "side": blocked["side"],
            "qty": blocked["qty"],
            "current_qty": blocked["current_qty"],
            "proposed_qty": blocked["proposed_qty"],
            "reason": blocked["reason"],
            "status": "risk_blocked",
        }
        human_logger.order_update(
            order_id="risk",
            status=f"blocked_{blocked['reason']}",
            client_order_id=f"{blocked['symbol']}:{blocked['side']}:{blocked['qty']}",
        )
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="order_update",
                payload=blocked_payload,
            )
        )

    prepared_orders, duplicate_blocked = prepare_orders(
        orders=orders,
        run_id=run_id,
        state_store=state_store,
        event_sink=event_sink,
        human_logger=human_logger,
        settings=settings,
        strategy=strategy,
        reference_prices=latest_prices,
    )
    human_logger.cycle_summary(
        strategy_id=strategy.strategy_id,
        raw_orders=len(raw_orders),
        risk_orders=len(orders),
        prepared_orders=len(prepared_orders),
        risk_blocked=len(risk_blocked),
        duplicate_blocked=len(duplicate_blocked),
        details=pnl_metrics,
    )

    pre_submit_payload: dict[str, Any] = {
        "stage": "pre_submit",
        "portfolio": serialize_portfolio(portfolio),
        "pnl": pnl_metrics,
        "latest_prices": latest_prices,
        "positions": serialize_positions(positions),
        "targets": dict(sorted(targets.items())),
        "raw_orders": serialize_orders(raw_orders),
        "risk_orders": serialize_orders(orders),
        "prepared_orders": serialize_orders(prepared_orders),
        "risk_blocked": risk_blocked,
        "duplicate_blocked": duplicate_blocked,
        "raw_order_count": len(raw_orders),
        "risk_order_count": len(orders),
        "prepared_order_count": len(prepared_orders),
    }
    if decision_details:
        pre_submit_payload["decisions"] = decision_details

    event_sink.emit(
        TradeEvent(
            run_id=run_id,
            mode=settings.mode,
            strategy_id=strategy.strategy_id,
            event_type="cycle_summary",
            payload=pre_submit_payload,
        )
    )

    if not prepared_orders:
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
        price_details = extract_receipt_price_details(receipt)
        human_logger.order_update(
            receipt.order_id,
            receipt.status,
            receipt.client_order_id,
            details=price_details or None,
        )
        payload: dict[str, Any] = {
            "order_id": receipt.order_id,
            "client_order_id": receipt.client_order_id,
            "symbol": receipt.symbol,
            "side": receipt.side.value,
            "qty": receipt.qty,
            "status": receipt.status,
        }
        payload.update(price_details)
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="order_update",
                payload=payload,
            )
        )
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
    reference_prices: dict[str, float] | None = None,
) -> tuple[list[OrderRequest], list[dict[str, Any]]]:
    """Attach client ids and persist intent before submission."""
    prepared: list[OrderRequest] = []
    duplicate_blocked: list[dict[str, Any]] = []
    for index, order in enumerate(orders):
        if state_store.has_active_intent(order.symbol, order.side.value, order.qty):
            blocked_payload = {
                "symbol": order.symbol,
                "side": order.side.value,
                "qty": order.qty,
                "status": "duplicate_blocked",
                "reason": "active_intent",
            }
            human_logger.order_update(
                order_id="dedupe",
                status="duplicate_blocked",
                client_order_id=f"{order.symbol}:{order.side.value}:{order.qty}",
            )
            event_sink.emit(
                TradeEvent(
                    run_id=run_id,
                    mode=settings.mode,
                    strategy_id=strategy.strategy_id,
                    event_type="order_update",
                    payload=blocked_payload,
                )
            )
            duplicate_blocked.append(blocked_payload)
            continue
        client_order_id = build_client_order_id(run_id, index, order.symbol)
        order_with_id = replace(order, client_order_id=client_order_id)
        state_store.save_intended_order(run_id, order_with_id)
        reference_price = None
        if reference_prices is not None:
            reference_price = reference_prices.get(order.symbol)
        submit_details: dict[str, Any] = {}
        if reference_price is not None:
            submit_details["reference_price"] = round(reference_price, 6)
            submit_details["est_notional"] = round(reference_price * order.qty, 4)

        human_logger.order_submit(
            order.symbol,
            order.side.value,
            order.qty,
            client_order_id,
            details=submit_details or None,
        )
        payload: dict[str, Any] = {
            "symbol": order_with_id.symbol,
            "side": order_with_id.side.value,
            "qty": order_with_id.qty,
            "client_order_id": order_with_id.client_order_id,
        }
        payload.update(submit_details)
        event_sink.emit(
            TradeEvent(
                run_id=run_id,
                mode=settings.mode,
                strategy_id=strategy.strategy_id,
                event_type="order_submit",
                payload=payload,
            )
        )
        prepared.append(order_with_id)
    return prepared, duplicate_blocked


def build_client_order_id(run_id: str, index: int, symbol: str) -> str:
    """Generate unique client order id to satisfy broker uniqueness requirements."""
    return f"{run_id[:10]}-{symbol.upper()}-{index}-{uuid4().hex[:8]}"


def summarize_decision_details(
    bars: Any,
    lookback_bars: int,
    target_qty: int,
    current_qty: int,
) -> dict[str, Any]:
    """Build per-symbol diagnostics used in cycle analysis."""
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


def compute_equity_metrics(
    run_metrics: dict[str, float | None],
    equity: float,
) -> dict[str, float]:
    """Track equity-based PnL from run start and previous cycle."""
    start_equity = run_metrics.get("start_equity")
    previous_equity = run_metrics.get("previous_equity")

    if start_equity is None:
        start_equity = equity
        run_metrics["start_equity"] = equity
    if previous_equity is None:
        previous_equity = equity

    pnl_start = equity - start_equity
    pnl_prev = equity - previous_equity
    pnl_start_pct = (pnl_start / start_equity) if start_equity else 0.0

    run_metrics["previous_equity"] = equity
    return {
        "equity": round(equity, 4),
        "pnl_start": round(pnl_start, 4),
        "pnl_prev": round(pnl_prev, 4),
        "pnl_start_pct": round(pnl_start_pct, 6),
    }


def build_latest_prices(bars_by_symbol: dict[str, Any]) -> dict[str, float]:
    """Build latest close price map for reference pricing diagnostics."""
    latest_prices: dict[str, float] = {}
    for symbol, bars in sorted(bars_by_symbol.items()):
        if not hasattr(bars, "columns"):
            continue
        if "close" not in bars.columns:
            continue
        if len(bars) == 0:
            continue
        latest_prices[symbol] = round(float(bars["close"].iloc[-1]), 6)
    return latest_prices


def extract_receipt_price_details(receipt: Any) -> dict[str, Any]:
    """Extract price/timestamp metadata from broker receipt payloads."""
    raw = receipt.raw if isinstance(receipt.raw, dict) else {}
    filled_avg_price = _parse_optional_float(raw.get("filled_avg_price"))
    limit_price = _parse_optional_float(raw.get("limit_price"))
    stop_price = _parse_optional_float(raw.get("stop_price"))
    details: dict[str, Any] = {}

    if filled_avg_price is not None:
        details["filled_avg_price"] = round(filled_avg_price, 6)
        details["filled_notional"] = round(filled_avg_price * receipt.qty, 4)
    if limit_price is not None:
        details["limit_price"] = round(limit_price, 6)
    if stop_price is not None:
        details["stop_price"] = round(stop_price, 6)

    for field in ("submitted_at", "filled_at", "updated_at"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            details[field] = value

    return details


def _parse_optional_float(value: Any) -> float | None:
    """Parse optional numeric field from mixed broker payload values."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def find_risk_blocked_orders(
    raw_orders: list[OrderRequest],
    safe_orders: list[OrderRequest],
    portfolio: Any,
    limits: RiskLimits,
) -> list[dict[str, Any]]:
    """Compute which raw orders were removed by risk filters and why."""
    safe_counts = Counter(_order_signature(order) for order in safe_orders)
    blocked: list[dict[str, Any]] = []

    for order in raw_orders:
        signature = _order_signature(order)
        if safe_counts[signature] > 0:
            safe_counts[signature] -= 1
            continue

        current_qty = portfolio.positions.get(
            order.symbol,
            Position(symbol=order.symbol, qty=0),
        ).qty
        signed_delta = order.qty if order.side is OrderSide.BUY else -order.qty
        proposed_qty = current_qty + signed_delta
        if not limits.allow_short and proposed_qty < 0:
            reason = "short_disabled"
        elif abs(proposed_qty) > limits.max_abs_position_per_symbol:
            reason = "max_position_exceeded"
        else:
            reason = "filtered"

        blocked.append(
            {
                "symbol": order.symbol,
                "side": order.side.value,
                "qty": order.qty,
                "current_qty": current_qty,
                "proposed_qty": proposed_qty,
                "reason": reason,
            }
        )

    return blocked


def _order_signature(order: OrderRequest) -> tuple[str, str, int, str, str]:
    """Build a deterministic order signature for multiset comparisons."""
    return (
        order.symbol,
        order.side.value,
        order.qty,
        order.order_type,
        order.time_in_force,
    )


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
    return "stale_reconciled"


def build_broker(settings: Settings) -> Broker:
    """Select broker implementation based on mode."""
    if settings.mode == "backtest":
        return BacktestBroker(starting_cash=settings.backtest_starting_cash)
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required for live mode")
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

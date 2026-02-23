"""Runtime wiring and trading loop orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path
from time import perf_counter, sleep
from typing import Any
from uuid import uuid4

from algotrade.brokers.alpaca_paper import AlpacaPaperBroker
from algotrade.brokers.backtest_broker import BacktestBroker
from algotrade.brokers.base import Broker
from algotrade.config import Settings
from algotrade.data.alpaca_market_data import AlpacaMarketDataProvider
from algotrade.data.base import MarketDataProvider
from algotrade.data.csv_data import CsvDataProvider
from algotrade.data.yfinance_data import YFinanceDataProvider
from algotrade.domain.events import TradeEvent
from algotrade.domain.models import (
    OrderRequest,
    OrderSide,
    PortfolioSnapshot,
    Position,
    RiskLimits,
)
from algotrade.execution.engine import apply_risk_gates, compute_orders
from algotrade.logging.event_sink import JsonlEventSink, generate_plotly_report
from algotrade.logging.logger import HumanLogger
from algotrade.state.sqlite_store import SqliteStateStore
from algotrade.state.store import OrderIntentRecord, StateStore
from algotrade.strategy_core.base import Strategy
from algotrade.strategy_core.registry import create_strategy


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

    def has_active_intent(self, symbol: str, side: str, qty: float) -> bool:
        _ = (symbol, side, qty)
        return False

    def close(self) -> None:
        return None


def show_portfolio(settings: Settings) -> int:
    """List current portfolio balances and positions."""
    if settings.mode != "live":
        raise ValueError("--portfolio requires --mode live")

    broker = build_broker(settings)
    human_logger = HumanLogger(level=settings.log_level)
    run_id = uuid4().hex

    try:
        positions = broker.get_positions()
        portfolio = broker.get_portfolio()
        human_logger.run_started(
            run_id=run_id,
            mode=settings.mode,
            strategy_id="portfolio",
            symbols=sorted(positions),
        )
        human_logger.portfolio(
            cash=float(portfolio.cash),
            equity=float(portfolio.equity),
            buying_power=float(portfolio.buying_power),
        )
        human_logger.cash(float(portfolio.cash))
        if not positions:
            human_logger.order_update(order_id="portfolio", status="no_positions")
            return 0
        get_positions_details = getattr(broker, "get_positions_details", None)
        if callable(get_positions_details):
            detailed_positions = get_positions_details()
            if detailed_positions:
                detailed_symbols: set[str] = set()
                for item in sorted(
                    (entry for entry in detailed_positions if isinstance(entry, dict)),
                    key=lambda entry: str(entry.get("symbol", "")),
                ):
                    symbol = str(item.get("symbol", "")).upper()
                    if not symbol:
                        continue
                    detailed_symbols.add(symbol)
                    qty = _parse_optional_float(item.get("qty"))
                    market_value = _parse_optional_float(item.get("market_value"))
                    cost_basis = _parse_optional_float(item.get("cost_basis"))
                    unrealized_pl = _parse_optional_float(item.get("unrealized_pl"))
                    if qty is not None:
                        human_logger.position_exposure(
                            symbol=symbol,
                            qty=qty,
                            market_value=market_value,
                            cost_basis=cost_basis,
                            unrealized_pl=unrealized_pl,
                        )
                        continue
                    fallback_qty = positions.get(symbol)
                    if fallback_qty is not None:
                        human_logger.position(symbol=symbol, qty=fallback_qty.qty)
                        continue
                    human_logger.position(symbol=symbol, qty=0)
                for symbol, position in sorted(positions.items()):
                    if symbol in detailed_symbols:
                        continue
                    human_logger.position(symbol=symbol, qty=position.qty)
                return 0
        for symbol, position in sorted(positions.items()):
            human_logger.position(symbol=symbol, qty=position.qty)
    except Exception as exc:
        human_logger.error(str(exc))
        return 1

    return 0


def liquidate(settings: Settings) -> int:
    """Close all open positions by submitting offsetting orders."""
    if settings.mode != "live":
        raise ValueError("--liquidate requires --mode live")

    broker = build_broker(settings)
    human_logger = HumanLogger(level=settings.log_level)
    run_id = uuid4().hex

    try:
        positions = broker.get_positions()
        human_logger.run_started(
            run_id=run_id,
            mode=settings.mode,
            strategy_id="liquidate",
            symbols=sorted(positions),
        )
        if not positions:
            human_logger.order_update(
                order_id="liquidate",
                status="no_positions",
            )
            portfolio = broker.get_portfolio()
            human_logger.portfolio(
                cash=float(portfolio.cash),
                equity=float(portfolio.equity),
                buying_power=float(portfolio.buying_power),
            )
            return 0

        # Prefer Alpaca's server-side close endpoint so fractional crypto positions are closed
        # exactly and reserved balances/open orders are handled in a single call.
        close_all_positions = getattr(broker, "close_all_positions", None)
        if callable(close_all_positions):
            raw_updates = close_all_positions(cancel_orders=True)
            for update in raw_updates:
                symbol = str(update.get("symbol", ""))
                qty = _parse_optional_float(update.get("qty"))
                side = str(update.get("side", ""))
                if symbol and qty is not None and side:
                    qty_display = abs(float(qty))
                    if qty_display <= 0:
                        qty_display = 0.0001
                    human_logger.order_submit(
                        symbol=symbol,
                        side=side,
                        qty=qty_display,
                        client_order_id="liquidate",
                    )
                human_logger.order_update(
                    order_id=str(update.get("id", "liquidate")),
                    status=str(update.get("status", "submitted")),
                    client_order_id=(str(update.get("client_order_id", "")) or None),
                    details={
                        key: update[key]
                        for key in ("filled_avg_price", "submitted_at", "filled_at", "updated_at")
                        if key in update
                    }
                    or None,
                )
            portfolio = broker.get_portfolio()
            human_logger.portfolio(
                cash=float(portfolio.cash),
                equity=float(portfolio.equity),
                buying_power=float(portfolio.buying_power),
            )
            return 0

        orders = build_liquidation_orders(
            positions=positions,
            default_order_type=settings.default_order_type,
        )
        for order in orders:
            human_logger.order_submit(
                symbol=order.symbol,
                side=order.side.value,
                qty=order.qty,
                client_order_id="liquidate",
            )
        receipts = broker.submit_orders(orders)
        for receipt in receipts:
            details = extract_receipt_price_details(receipt)
            human_logger.order_update(
                order_id=receipt.order_id,
                status=receipt.status,
                client_order_id=receipt.client_order_id,
                details=details or None,
            )
        portfolio = broker.get_portfolio()
        human_logger.portfolio(
            cash=float(portfolio.cash),
            equity=float(portfolio.equity),
            buying_power=float(portfolio.buying_power),
        )
    except Exception as exc:
        human_logger.error(str(exc))
        return 1

    return 0


def run(settings: Settings) -> int:
    """Run algorithmic trading in live or backtest mode."""
    strategy = create_strategy(settings.strategy, settings)
    resolved_symbols = resolve_strategy_symbols(settings.symbols, strategy)
    if resolved_symbols != settings.symbols:
        settings = settings.with_overrides(symbols=resolved_symbols)
    data_provider = build_data_provider(settings, strategy)
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
        if settings.mode == "backtest":
            total_steps = resolve_backtest_total_steps(settings, data_provider)
            progress_interval = resolve_backtest_progress_interval(total_steps)
            started_at = perf_counter()
            for index in range(total_steps):
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
                completed_steps = index + 1
                if should_emit_backtest_progress(
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    progress_interval=progress_interval,
                ):
                    elapsed_seconds = perf_counter() - started_at
                    steps_per_second = (
                        float(completed_steps) / elapsed_seconds if elapsed_seconds > 0 else 0.0
                    )
                    eta_seconds: float | None = None
                    if steps_per_second > 0 and completed_steps < total_steps:
                        eta_seconds = float(total_steps - completed_steps) / steps_per_second
                    human_logger.backtest_progress(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                        elapsed_seconds=elapsed_seconds,
                        steps_per_second=steps_per_second,
                        eta_seconds=eta_seconds,
                    )
        else:
            pass_limit = settings.live_pass_limit()
            if pass_limit is None:
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
                for index in range(pass_limit):
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
                    if index < pass_limit - 1:
                        sleep(float(settings.interval_seconds))
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
            try:
                final_equity = float(broker.get_portfolio().equity)
                start_equity = run_metrics.get("start_equity")
                if start_equity is None:
                    start_equity = final_equity
                pnl = final_equity - float(start_equity)
                pnl_pct = (pnl / float(start_equity)) if float(start_equity) else 0.0
                human_logger.run_pnl(
                    equity=final_equity,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    start_equity=float(start_equity),
                )
            except Exception:
                pass
            generate_plotly_report(str(events_path), str(report_path))
        finally:
            state_store.close()

    return exit_code


def build_liquidation_orders(
    positions: dict[str, Position],
    default_order_type: str = "market",
) -> list[OrderRequest]:
    """Build offsetting orders that flatten all non-zero positions."""
    orders: list[OrderRequest] = []
    for symbol, position in sorted(positions.items()):
        if position.qty == 0:
            continue
        side = OrderSide.SELL if position.qty > 0 else OrderSide.BUY
        orders.append(
            OrderRequest(
                symbol=symbol,
                qty=abs(position.qty),
                side=side,
                order_type=default_order_type,
            )
        )
    return orders


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
    signal_targets = strategy.decide_targets(bars_by_symbol, portfolio)
    targets = resolve_target_quantities(
        signal_targets=signal_targets,
        latest_prices=latest_prices,
        settings=settings,
        strategy=strategy,
        portfolio_snapshot=portfolio,
    )
    decision_details: dict[str, dict[str, Any]] = {}
    include_details = settings.mode == "backtest" or strategy.strategy_id == "scalping"
    lookback_bars = strategy_diagnostic_lookback_bars(strategy)

    for symbol, target in sorted(targets.items()):
        current_qty = positions.get(symbol, Position(symbol=symbol, qty=0)).qty
        target_signal = float(signal_targets.get(symbol, 0.0))
        payload: dict[str, Any] = {
            "symbol": symbol,
            "target_signal": target_signal,
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
            details["target_signal"] = target_signal
            if strategy.strategy_id == "scalping":
                params = getattr(strategy, "params", None)
                fast_ema_period = getattr(params, "fast_ema_period", None)
                slow_ema_period = getattr(params, "slow_ema_period", None)
                rsi_period = getattr(params, "rsi_period", None)
                allow_short = getattr(params, "allow_short", None)
                if fast_ema_period is not None:
                    details["scalping_fast_ema_period"] = int(fast_ema_period)
                if slow_ema_period is not None:
                    details["scalping_slow_ema_period"] = int(slow_ema_period)
                if rsi_period is not None:
                    details["scalping_rsi_period"] = int(rsi_period)
                if allow_short is not None:
                    details["scalping_allow_short"] = bool(allow_short)
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
        min_trade_qty=settings.min_trade_qty,
        qty_precision=settings.qty_precision,
    )
    risk_limits = RiskLimits(
        max_abs_position_per_symbol=settings.max_abs_position_per_symbol,
        allow_short=settings.allow_short,
    )
    non_shortable_symbols = resolve_non_shortable_symbols(settings, raw_orders)
    orders = apply_risk_gates(
        raw_orders,
        portfolio,
        risk_limits,
        non_shortable_symbols=non_shortable_symbols,
    )
    risk_blocked = find_risk_blocked_orders(
        raw_orders,
        orders,
        portfolio,
        risk_limits,
        non_shortable_symbols=non_shortable_symbols,
    )

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
        "target_signals": dict(sorted(signal_targets.items())),
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
    target_qty: float,
    current_qty: float,
) -> dict[str, Any]:
    """Build per-symbol diagnostics used in cycle analysis."""
    details: dict[str, Any] = {
        "delta_qty": round(float(target_qty) - float(current_qty), 8),
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


def resolve_target_quantities(
    signal_targets: dict[str, float],
    latest_prices: dict[str, float],
    settings: Settings,
    strategy: Strategy | None = None,
    portfolio_snapshot: PortfolioSnapshot | None = None,
) -> dict[str, float]:
    """Convert strategy targets into broker-facing position quantities."""
    resolved: dict[str, float] = {}
    sizing_method = settings.order_sizing_method.strip().lower()
    strategy_trade_bounds = strategy_trade_size_bounds(strategy)
    strategy_signal_cap = strategy_signal_scale(strategy)
    equity = _resolve_equity(portfolio_snapshot)
    for symbol, signal in sorted(signal_targets.items()):
        signal_value = float(signal)
        target_qty: float
        if sizing_method == "notional":
            if signal_value == 0:
                target_qty = 0.0
            elif strategy_trade_bounds is not None and equity is not None:
                price = latest_prices.get(symbol)
                if price is None or price <= 0:
                    target_qty = 0.0
                else:
                    min_fraction, max_fraction = strategy_trade_bounds
                    signal_strength = _signal_strength(
                        signal_value=signal_value,
                        signal_cap=strategy_signal_cap,
                    )
                    target_fraction = min_fraction + (
                        (max_fraction - min_fraction) * signal_strength
                    )
                    target_notional = equity * target_fraction
                    target_qty = (target_notional / price) * (1 if signal_value > 0 else -1)
            else:
                price = latest_prices.get(symbol)
                if price is None or price <= 0:
                    target_qty = 0.0
                else:
                    target_qty = (signal_value * settings.order_notional_usd) / price
        else:
            target_qty = signal_value

        rounded_target = _round_qty(target_qty, settings.qty_precision)
        if abs(rounded_target) < settings.min_trade_qty:
            rounded_target = 0.0
        resolved[symbol] = rounded_target
    return resolved


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


def _round_qty(value: float, precision: int) -> float:
    rounded = round(float(value), max(0, int(precision)))
    if abs(rounded) < 1e-9:
        return 0.0
    return rounded


def _qty_key(value: float, precision: int = 8) -> str:
    return f"{_round_qty(value, precision):.{max(0, precision)}f}"


def serialize_positions(positions: dict[str, Position]) -> dict[str, float]:
    """Convert position objects into a deterministic, JSON-friendly mapping."""
    return {symbol: _round_qty(position.qty, 8) for symbol, position in sorted(positions.items())}


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


def resolve_non_shortable_symbols(settings: Settings, orders: list[OrderRequest]) -> set[str]:
    """Identify symbols that should be treated as long-only in current runtime context."""
    if settings.mode != "live":
        return set()
    if settings.effective_data_source() != "alpaca":
        return set()

    blocked_symbols: set[str] = set()
    for order in orders:
        symbol = str(order.symbol).strip().upper()
        if not symbol:
            continue
        if AlpacaPaperBroker._is_crypto_symbol(symbol):
            blocked_symbols.add(symbol)
    return blocked_symbols


def find_risk_blocked_orders(
    raw_orders: list[OrderRequest],
    safe_orders: list[OrderRequest],
    portfolio: Any,
    limits: RiskLimits,
    non_shortable_symbols: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Compute which raw orders were removed by risk filters and why."""
    blocked_short_symbols = {symbol.upper() for symbol in (non_shortable_symbols or set())}
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
        symbol_forbids_short = order.symbol.upper() in blocked_short_symbols
        if symbol_forbids_short and proposed_qty < 0:
            reason = "asset_not_shortable"
        elif not limits.allow_short and proposed_qty < 0:
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


def _order_signature(order: OrderRequest) -> tuple[str, str, str, str, str]:
    """Build a deterministic order signature for multiset comparisons."""
    return (
        order.symbol,
        order.side.value,
        _qty_key(order.qty),
        order.order_type,
        order.time_in_force,
    )


def build_bars_by_symbol(symbols: list[str], data_provider: MarketDataProvider) -> dict[str, Any]:
    """Fetch bar data for all symbols."""
    bars_by_symbol: dict[str, Any] = {}
    for symbol in symbols:
        bars_by_symbol[symbol] = data_provider.get_bars(symbol)
    return bars_by_symbol


def resolve_backtest_total_steps(settings: Settings, data_provider: MarketDataProvider) -> int:
    """Resolve walk-forward step count for a backtest run."""
    total_steps = 1
    get_total_steps = getattr(data_provider, "walk_forward_total_steps", None)
    if callable(get_total_steps):
        total_steps = int(get_total_steps(settings.symbols))
    cap = settings.backtest_step_cap()
    if cap is not None:
        total_steps = min(total_steps, cap)
    return max(1, total_steps)


def resolve_backtest_progress_interval(total_steps: int) -> int:
    """Resolve progress log cadence to keep output informative but lightweight."""
    if total_steps <= 20:
        return 1
    return max(1, total_steps // 20)


def should_emit_backtest_progress(
    completed_steps: int,
    total_steps: int,
    progress_interval: int,
) -> bool:
    """Determine whether to emit a backtest progress line."""
    return (
        completed_steps == 1
        or completed_steps == total_steps
        or completed_steps % max(1, progress_interval) == 0
    )


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
    get_order_status = getattr(broker, "get_order_status", None)

    for intent in active_intents:
        broker_status: str | None = None
        if callable(get_order_status) and intent.broker_order_id:
            try:
                value = get_order_status(intent.broker_order_id)
                if isinstance(value, str):
                    broker_status = value.strip().lower() or None
            except Exception:
                broker_status = None
        status = resolve_intent_status(
            intent,
            open_client_ids,
            positions,
            broker_status=broker_status,
        )
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
    broker_status: str | None = None,
) -> str:
    """Determine reconciled status for a persisted intent."""
    epsilon = 1e-6
    if intent.client_order_id in open_client_ids:
        return "submitted"
    if broker_status in {"filled", "partially_filled"}:
        return "filled_reconciled"
    if broker_status in {"canceled", "cancelled", "rejected", "expired"}:
        return "closed_reconciled"
    position_qty = positions.get(intent.symbol, Position(symbol=intent.symbol, qty=0)).qty
    if intent.side == OrderSide.BUY.value and position_qty + epsilon >= intent.qty:
        return "filled_reconciled"
    if intent.side == OrderSide.SELL.value and position_qty - epsilon <= -intent.qty:
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


def build_data_provider(settings: Settings, strategy: Strategy) -> MarketDataProvider:
    """Select data provider from mode and data source."""
    source = settings.effective_data_source()
    if source == "csv":
        walk_forward = settings.mode == "backtest"
        warmup_bars = strategy_warmup_bars(strategy)
        missing_data_fetcher = None
        if settings.mode == "backtest":
            fallback_provider = YFinanceDataProvider(timeframe=settings.timeframe)
            missing_data_fetcher = fallback_provider.get_bars
        return CsvDataProvider(
            data_dir=settings.historical_data_dir,
            walk_forward=walk_forward,
            warmup_bars=warmup_bars,
            missing_data_fetcher=missing_data_fetcher,
            persist_downloaded_bars=settings.mode == "backtest",
        )
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required for Alpaca data")
    return AlpacaMarketDataProvider(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        data_base_url=settings.alpaca_data_url,
        timeframe=settings.timeframe,
    )


def strategy_diagnostic_lookback_bars(strategy: Strategy) -> int:
    """Resolve lookback horizon from strategy params for decision diagnostics."""
    params = getattr(strategy, "params", None)
    candidates = [1]
    for field in ("lookback_bars", "slow_ema_period", "rsi_period"):
        value = getattr(params, field, None)
        if isinstance(value, (int, float)) and value > 0:
            candidates.append(int(value))
    return max(candidates)


def strategy_trade_size_bounds(strategy: Strategy | None) -> tuple[float, float] | None:
    """Resolve strategy-level min/max trade size percentages into decimal fractions."""
    if strategy is None:
        return None
    params = getattr(strategy, "params", None)
    min_pct = getattr(params, "min_trade_size_pct", None)
    max_pct = getattr(params, "max_trade_size_pct", None)
    if not isinstance(min_pct, (int, float)) or not isinstance(max_pct, (int, float)):
        return None
    min_pct_value = float(min_pct)
    max_pct_value = float(max_pct)
    if min_pct_value <= 0 or max_pct_value <= 0:
        return None
    if min_pct_value > max_pct_value:
        return None
    return (min_pct_value / 100.0, max_pct_value / 100.0)


def strategy_signal_scale(strategy: Strategy | None) -> float:
    """Resolve the signal magnitude that maps to full trade size."""
    if strategy is None:
        return 1.0
    params = getattr(strategy, "params", None)
    for field in ("max_abs_qty", "target_qty"):
        value = getattr(params, field, None)
        if isinstance(value, (int, float)) and float(value) > 0:
            return float(value)
    return 1.0


def resolve_strategy_symbols(configured_symbols: list[str], strategy: Strategy | None) -> list[str]:
    """Resolve runtime symbols by reconciling configured and strategy-declared symbols."""
    configured = normalize_symbol_list(configured_symbols)
    if strategy is None:
        return configured

    get_declared_symbols = getattr(strategy, "declared_symbols", None)
    if not callable(get_declared_symbols):
        return configured

    declared = normalize_symbol_list(get_declared_symbols())
    if not declared:
        return configured

    configured_set = set(configured)
    if configured_set.intersection(declared):
        return normalize_symbol_list([*configured, *declared])
    return declared


def normalize_symbol_list(symbols: list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalize symbols to uppercase and de-duplicate while preserving order."""
    if symbols is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _signal_strength(signal_value: float, signal_cap: float) -> float:
    """Convert signed signal into a normalized 0..1 strength score."""
    if abs(signal_value) <= 1e-12:
        return 0.0
    if signal_cap <= 0:
        return 1.0
    return max(0.0, min(abs(float(signal_value)) / float(signal_cap), 1.0))


def _resolve_equity(portfolio_snapshot: PortfolioSnapshot | None) -> float | None:
    if portfolio_snapshot is None:
        return None
    equity = float(portfolio_snapshot.equity)
    if equity <= 0:
        return None
    return equity


def strategy_warmup_bars(strategy: Strategy) -> int:
    """Resolve minimum historical bars needed to run the strategy."""
    params = getattr(strategy, "params", None)
    candidates = [2]
    for field in ("lookback_bars", "slow_ema_period", "rsi_period"):
        value = getattr(params, field, None)
        if isinstance(value, (int, float)) and value > 0:
            candidates.append(int(value) + 1)
    return max(candidates)


def build_state_store(settings: Settings) -> StateStore:
    """Select state store implementation from mode."""
    if settings.mode == "backtest":
        return NoopStateStore()
    return SqliteStateStore(settings.state_db_path)

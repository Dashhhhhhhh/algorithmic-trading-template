"""Simple historical backtest runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from app.strategy.base import Signal, Strategy


@dataclass(frozen=True)
class BacktestResult:
    """Summary metrics for one symbol backtest."""

    symbol: str
    start_equity: float
    end_equity: float
    pnl: float
    pnl_pct: float
    trades: int


def run_backtest_for_symbol(
    symbol: str,
    bars: pd.DataFrame,
    strategy: Strategy,
    qty: int = 1,
    allow_short: bool = True,
    starting_cash: float = 100_000.0,
) -> BacktestResult:
    """Run a naive close-to-close backtest for one symbol.

    This is intentionally simple for club learning:
    - Signals are computed on data up to current bar.
    - Any position change fills at current close.
    - No slippage/fees/borrow costs.
    """
    logger = logging.getLogger("algotrade.backtest")
    if bars.empty:
        return BacktestResult(symbol, starting_cash, starting_cash, 0.0, 0.0, 0)

    cash = starting_cash
    position = 0
    trades = 0

    # Need a warm-up buffer; strategy returns HOLD until enough data.
    for i in range(2, len(bars)):
        view = bars.iloc[: i + 1]
        close = float(view["close"].iloc[-1])
        signal = strategy.generate_signal(symbol=symbol, bars=view)

        target = position
        if signal == Signal.BUY:
            target = qty
        elif signal == Signal.SELL:
            target = -qty if allow_short else 0

        delta = target - position
        if delta != 0:
            cash -= delta * close
            position = target
            trades += 1
            timestamp = view.index[-1]
            equity = cash + (position * close)
            logger.info(
                "%s backtest trade #%s | time=%s signal=%s delta=%s price=%.2f position=%s cash=%.2f equity=%.2f",
                symbol,
                trades,
                timestamp,
                signal.value,
                delta,
                close,
                position,
                cash,
                equity,
            )

    last_close = float(bars["close"].iloc[-1])
    end_equity = cash + (position * last_close)
    pnl = end_equity - starting_cash
    pnl_pct = (pnl / starting_cash) * 100 if starting_cash > 0 else 0.0

    return BacktestResult(
        symbol=symbol,
        start_equity=starting_cash,
        end_equity=end_equity,
        pnl=pnl,
        pnl_pct=pnl_pct,
        trades=trades,
    )

"""
Lightweight backtesting engine.

Replays OHLCV candles, simulates fees and slippage, generates equity curve,
and computes performance metrics.
"""

import asyncio
from typing import Any, Optional

from backtest.models import TradeRecord
from backtest.metrics import compute_metrics
from backtest.report import PerformanceReport


class BacktestEngine:
    """Lightweight backtester with basic performance metrics."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission: float = 0.001,      # fraction (0.1%)
        slippage: float = 0.001,        # fraction (0.1%)
        risk_per_trade: float = 0.02,   # 2% of capital per trade
    ) -> None:
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.risk_per_trade = risk_per_trade

    async def run(
        self,
        ohlcv: list[list],
        strategy: Any,   # must implement async get_signal(symbol, ohlcv_subset)
        symbol: str = "UNKNOWN",
    ) -> PerformanceReport:
        """
        Run the backtest over OHLCV data.

        ``ohlcv`` is a list of candles in standard format:
            [timestamp, open, high, low, close, volume]

        ``strategy`` must have an async ``get_signal(symbol, ohlcv_list)`` method
        that returns 'long', 'short', 'close', or 'hold'.

        Returns a PerformanceReport with all metrics.
        """
        if len(ohlcv) < 2:
            return PerformanceReport.empty()

        capital = self.initial_capital
        equity_curve: list[float] = [capital]

        trades: list[TradeRecord] = []

        # current position state
        position_side: Optional[str] = None   # 'long' / 'short'
        entry_price: float = 0.0
        entry_time: float = 0.0
        position_size: float = 0.0  # absolute quantity (always positive)

        for i in range(len(ohlcv)):
            candle = ohlcv[i]
            close = candle[4]
            timestamp = candle[0]

            # Provide the strategy with all data up to current index
            signal = await strategy.get_signal(symbol, ohlcv[: i + 1])

            # ---- OPEN NEW POSITION ----
            if position_side is None and signal in ("long", "short"):
                side = signal
                # Apply slippage to execution price
                exec_price = (
                    close * (1 + self.slippage) if side == "long"
                    else close * (1 - self.slippage)
                )

                # Position size based on risk per trade of current capital
                risk_amount = capital * self.risk_per_trade
                quantity = risk_amount / exec_price
                if quantity <= 0:
                    continue

                # Deduct commission (on notional)
                notional = quantity * exec_price
                commission = notional * self.commission
                capital -= commission

                if side == "long":
                    capital -= notional
                else:
                    capital += notional  # credit for short sale

                position_side = side
                entry_price = exec_price
                entry_time = timestamp
                position_size = quantity

            # ---- CLOSE EXISTING POSITION ----
            elif position_side is not None and signal == "close":
                # Close at close price with slippage
                exec_price = (
                    close * (1 - self.slippage) if position_side == "long"
                    else close * (1 + self.slippage)
                )

                notional = position_size * exec_price
                commission = notional * self.commission

                if position_side == "long":
                    pnl = (exec_price - entry_price) * position_size - commission
                    capital += exec_price * position_size - commission
                else:
                    pnl = (entry_price - exec_price) * position_size - commission
                    capital -= exec_price * position_size + commission

                trades.append(TradeRecord(
                    symbol=symbol,
                    side=position_side,
                    entry_time=entry_time,
                    exit_time=timestamp,
                    entry_price=entry_price,
                    exit_price=exec_price,
                    quantity=position_size,
                    pnl=pnl,
                    commission=commission,
                ))

                # Reset position
                position_side = None
                entry_price = 0.0
                entry_time = 0.0
                position_size = 0.0

            # Record equity after each candle
            if position_side is not None:
                if position_side == "long":
                    unrealized = (close - entry_price) * position_size
                else:
                    unrealized = (entry_price - close) * position_size
                current_equity = capital + unrealized
            else:
                current_equity = capital

            equity_curve.append(current_equity)

        # Force‑close any leftover position at last close
        if position_side is not None:
            close = ohlcv[-1][4]  # last close
            timestamp = ohlcv[-1][0]
            exec_price = (
                close * (1 - self.slippage) if position_side == "long"
                else close * (1 + self.slippage)
            )
            notional = position_size * exec_price
            commission = notional * self.commission
            if position_side == "long":
                pnl = (exec_price - entry_price) * position_size - commission
                capital += exec_price * position_size - commission
            else:
                pnl = (entry_price - exec_price) * position_size - commission
                capital -= exec_price * position_size + commission

            trades.append(TradeRecord(
                symbol=symbol,
                side=position_side,
                entry_time=entry_time,
                exit_time=timestamp,
                entry_price=entry_price,
                exit_price=exec_price,
                quantity=position_size,
                pnl=pnl,
                commission=commission,
            ))
            equity_curve[-1] = capital

        # Compute metrics
        metrics = compute_metrics(
            initial_capital=self.initial_capital,
            final_capital=capital,
            equity_curve=equity_curve,
            trades=trades,
        )

        return PerformanceReport(
            initial_capital=self.initial_capital,
            final_capital=capital,
            total_pnl=capital - self.initial_capital,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
        )

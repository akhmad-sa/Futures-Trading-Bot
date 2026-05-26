"""
Production-grade backtesting engine.

Replays OHLCV candles, simulates fees, slippage, and funding,
generates equity curve, and computes performance metrics.
Leverages a risk management module for position sizing and risk controls.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backtest.models import TradeRecord
from backtest.metrics import compute_metrics
from backtest.report import PerformanceReport
from core.models.candle import Candle
from risk.manager import RiskManager


class BacktestEngine:
    """
    Production-grade backtester for margin trading strategies.
    Simulates commissions, slippage, and funding fees.
    Integrates with a RiskManager for sophisticated risk control.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.001,
        funding_rate: float = 0.0,
        funding_interval_hours: int = 8,
    ) -> None:
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.funding_rate = funding_rate
        self.funding_interval_hours = funding_interval_hours

    async def run(
        self,
        ohlcv: list[list],
        strategy: Any,
        symbol: str = "UNKNOWN",
    ) -> PerformanceReport:
        """
        Run the backtest over OHLCV data.

        `ohlcv` is a list of candles in standard format:
            [timestamp, open, high, low, close, volume]
        Timestamp is expected in milliseconds.

        `strategy` must have an async `get_signal(symbol, ohlcv_list)` method
        that returns 'long', 'short', 'close', or 'hold'.

        Returns a PerformanceReport with all metrics.
        """
        if len(ohlcv) < 2:
            return PerformanceReport.empty()

        # Convert raw OHLCV into Candle objects for internal use
        candles: list[Candle] = []
        for raw in ohlcv:
            ts, o, h, l, c, v = raw
            candles.append(Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v))

        self.risk_manager.reset_all()

        balance = self.initial_capital
        equity_curve: list[float] = [balance]
        trades: list[TradeRecord] = []
        total_funding_fees = 0.0

        position_side: Optional[str] = None
        entry_price: float = 0.0
        entry_time: float = 0.0
        position_size: float = 0.0
        last_funding_time: Optional[datetime] = None

        for i in range(len(candles)):
            candle = candles[i]
            timestamp = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc)

            # --- Funding Simulation ---
            if self.funding_rate != 0 and position_side is not None:
                if last_funding_time is None:
                    entry_dt = datetime.fromtimestamp(entry_time / 1000, tz=timezone.utc)
                    hour_block = entry_dt.hour // self.funding_interval_hours
                    current_block_start_hour = hour_block * self.funding_interval_hours
                    last_funding_time = entry_dt.replace(
                        hour=current_block_start_hour, minute=0, second=0, microsecond=0
                    ) + timedelta(hours=self.funding_interval_hours)

                while timestamp >= last_funding_time:
                    notional = position_size * candle.close
                    funding_payment = notional * self.funding_rate
                    if position_side == "short":
                        funding_payment = -funding_payment

                    balance -= funding_payment
                    total_funding_fees += funding_payment
                    last_funding_time += timedelta(hours=self.funding_interval_hours)

            # --- Get Signal ---
            signal = await strategy.get_signal(symbol, ohlcv[: i + 1])

            # --- Open Position ---
            if position_side is None and signal in ("long", "short"):
                equity_before_trade = balance  # No unrealized PnL if no position
                can_open = self.risk_manager.can_open_position(
                    symbol=symbol,
                    side=signal,
                    price=candle.close,
                    current_positions_count=0,
                    current_capital=equity_before_trade,
                )
                if can_open:
                    exec_price = (
                        candle.close * (1 + self.slippage)
                        if signal == "long"
                        else candle.close * (1 - self.slippage)
                    )
                    quantity, _ = self.risk_manager.calculate_position_size(
                        capital=equity_before_trade, price=exec_price
                    )
                    if quantity > 0:
                        commission_cost = quantity * exec_price * self.commission
                        balance -= commission_cost
                        position_side = signal
                        entry_price = exec_price
                        entry_time = candle.timestamp
                        position_size = quantity

            # --- Close Position ---
            elif position_side is not None and signal == "close":
                exec_price = (
                    candle.close * (1 - self.slippage)
                    if position_side == "long"
                    else candle.close * (1 + self.slippage)
                )

                close_commission = position_size * exec_price * self.commission
                if position_side == "long":
                    gross_pnl = (exec_price - entry_price) * position_size
                else:
                    gross_pnl = (entry_price - exec_price) * position_size

                balance += gross_pnl - close_commission

                open_commission = position_size * entry_price * self.commission
                total_commission = open_commission + close_commission
                net_pnl = gross_pnl - total_commission

                trades.append(
                    TradeRecord(
                        symbol=symbol,
                        side=position_side,
                        entry_time=entry_time,
                        exit_time=candle.timestamp,
                        entry_price=entry_price,
                        exit_price=exec_price,
                        quantity=position_size,
                        pnl=net_pnl,
                        commission=total_commission,
                    )
                )
                self.risk_manager.record_trade_pnl(net_pnl)

                position_side = None
                last_funding_time = None

            # --- Record Equity ---
            if position_side is not None:
                if position_side == "long":
                    unrealized_pnl = (candle.close - entry_price) * position_size
                else:
                    unrealized_pnl = (entry_price - candle.close) * position_size
                equity_curve.append(balance + unrealized_pnl)
            else:
                equity_curve.append(balance)

        # --- Force-close any open position at the end ---
        if position_side is not None:
            last_candle = candles[-1]
            close = last_candle.close
            ts_ms = last_candle.timestamp
            exec_price = (
                close * (1 - self.slippage)
                if position_side == "long"
                else close * (1 + self.slippage)
            )

            close_commission = position_size * exec_price * self.commission
            if position_side == "long":
                gross_pnl = (exec_price - entry_price) * position_size
            else:
                gross_pnl = (entry_price - exec_price) * position_size

            balance += gross_pnl - close_commission

            open_commission = position_size * entry_price * self.commission
            total_commission = open_commission + close_commission
            net_pnl = gross_pnl - total_commission

            trades.append(
                TradeRecord(
                    symbol=symbol,
                    side=position_side,
                    entry_time=entry_time,
                    exit_time=ts_ms,
                    entry_price=entry_price,
                    exit_price=exec_price,
                    quantity=position_size,
                    pnl=net_pnl,
                    commission=total_commission,
                )
            )
            self.risk_manager.record_trade_pnl(net_pnl)
            equity_curve[-1] = balance

        # --- Compute Metrics & Report ---
        metrics = compute_metrics(
            initial_capital=self.initial_capital,
            final_capital=balance,
            equity_curve=equity_curve,
            trades=trades,
        )

        return PerformanceReport(
            initial_capital=self.initial_capital,
            final_capital=balance,
            total_pnl=balance - self.initial_capital,
            total_funding_fees=total_funding_fees,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
        )

"""
Production-grade backtesting engine.

Replays OHLCV candles fetched via the centralized MarketDataService,
simulates fees, slippage, and funding, generates equity curve, and
computes performance metrics. Leverages a risk management module for
position sizing and risk controls.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union

from backtest.models import TradeRecord
from backtest.metrics import compute_metrics
from backtest.report import PerformanceReport
from market_data import MarketDataService
from market_data.models.candle import Candle
from risk.manager import RiskManager


class BacktestEngine:
    """
    Production-grade backtester for margin trading strategies.
    Simulates commissions, slippage, and funding fees.
    Integrates with a RiskManager for sophisticated risk control.

    All candle data is obtained from MarketDataService, ensuring that
    backtest and live trading share the same candle flow.
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
        service: Union[MarketDataService, list],
        strategy: Any,
        symbol: str,
        timeframe: str,
        exchange: str = "default",
        limit: int = 10_000,
        since: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> PerformanceReport:
        """
        Run the backtest by replaying historical candles from MarketDataService.

        Parameters
        ----------
        service : MarketDataService or list
            The centralized market data service used to fetch candles,
            **or** a pre‑loaded list of :class:`Candle` objects.
        strategy : Any
            An object that has an async method ``get_signal(symbol, candles)``
            where ``candles`` is a list of :class:`Candle` objects.
            The method must return ``'long'``, ``'short'``, ``'close'``, or ``'hold'``.
        symbol : str
            Trading pair symbol (e.g. ``'BTC/USDT'``).
        timeframe : str
            Candle timeframe (e.g. ``'1h'``, ``'5m'``).
        exchange : str
            Exchange identifier (must be registered in the service).
        limit : int
            Maximum number of historical candles to retrieve.
        since : int, optional
            Starting timestamp in milliseconds. If ``None``, the service
            returns the most recent ``limit`` candles.
        start_time : int, optional
            Starting timestamp for the backtest period (milliseconds).
        end_time : int, optional
            Ending timestamp for the backtest period (milliseconds).

        Returns
        -------
        PerformanceReport
            Report containing all performance metrics and the equity curve.
        """
        # -----------------------------------------------------------------
        # Accept either a MarketDataService or a pre‑loaded list of candles
        # -----------------------------------------------------------------
        if isinstance(service, list):
            candles: List[Candle] = service
        else:
            candles = await service.get_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                since=since,
                start_time=start_time,
                end_time=end_time,
            )
        if len(candles) < 2:
            return PerformanceReport.empty()

        # -----------------------------------------------------------------
        # Initialise state
        # -----------------------------------------------------------------
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

        # -----------------------------------------------------------------
        # Replay candles in order – deterministic replay
        # -----------------------------------------------------------------
        for i in range(len(candles)):
            candle = candles[i]
            timestamp = datetime.fromtimestamp(
                candle.timestamp / 1000, tz=timezone.utc
            )

            # --- Funding simulation ---------------------------------------
            if self.funding_rate != 0 and position_side is not None:
                if last_funding_time is None:
                    entry_dt = datetime.fromtimestamp(
                        entry_time / 1000, tz=timezone.utc
                    )
                    hour_block = entry_dt.hour // self.funding_interval_hours
                    current_block_start_hour = hour_block * self.funding_interval_hours
                    last_funding_time = entry_dt.replace(
                        hour=current_block_start_hour,
                        minute=0,
                        second=0,
                        microsecond=0,
                    ) + timedelta(hours=self.funding_interval_hours)

                while timestamp >= last_funding_time:
                    notional = position_size * candle.close
                    funding_payment = notional * self.funding_rate
                    if position_side == "short":
                        funding_payment = -funding_payment

                    balance -= funding_payment
                    total_funding_fees += funding_payment
                    last_funding_time += timedelta(hours=self.funding_interval_hours)

            # --- Get signal from strategy (receives Candle list) ----------
            signal = await strategy.get_signal(symbol, candles[: i + 1])

            # --- Open position --------------------------------------------
            if position_side is None and signal in ("long", "short"):
                equity_before_trade = balance  # No unrealised PnL with no position
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

            # --- Close position -------------------------------------------
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

            # --- Record equity curve --------------------------------------
            if position_side is not None:
                if position_side == "long":
                    unrealized_pnl = (candle.close - entry_price) * position_size
                else:
                    unrealized_pnl = (entry_price - candle.close) * position_size
                equity_curve.append(balance + unrealized_pnl)
            else:
                equity_curve.append(balance)

        # --- Force-close any open position at the end --------------------
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

        # --- Compute metrics & report ------------------------------------
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

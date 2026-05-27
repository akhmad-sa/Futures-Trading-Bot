"""
Production-grade backtesting engine.

Replays OHLCV candles fetched via the centralized MarketDataService,
simulates maker/taker fees, slippage, funding, stop loss, take profit,
and leverage.  Generates equity curve and computes performance metrics.
Leverages a risk management module for position sizing and risk controls.
Uses SimulationClock for deterministic time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backtest.models import TradeRecord
from backtest.metrics import compute_metrics
from backtest.report import PerformanceReport
from market_data import MarketDataService
from market_data.models.candle import Candle
from risk.manager import RiskManager
from simulation.config import SimulationConfig
from simulation.fee_model import FeeModel
from simulation.slippage_model import SlippageModel
from simulation.funding_model import FundingModel
from simulation.latency_model import LatencyModel
from core.clock import SimulationClock


@dataclass
class RiskConfig:
    """Risk parameters applied during backtest."""
    max_position_size: float = 1.0       # fraction of capital (0..1)
    max_leverage: float = 1.0
    stop_loss_pct: float = 0.02          # 2% stop loss
    take_profit_pct: float = 0.04        # 4% take profit
    max_drawdown_pct: float = 0.20       # 20% max drawdown


class BacktestEngine:
    """
    Production-grade backtester for margin trading strategies.
    Simulates commissions, slippage, funding fees, stop loss, take profit,
    and leverage.  Integrates with a RiskManager for sophisticated risk control.

    All candle data is obtained from MarketDataService, ensuring that
    backtest and live trading share the same candle flow.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        initial_capital: float = 10_000.0,
        risk_config: Optional[RiskConfig] = None,
        simulation_config: Optional[SimulationConfig] = None,
        verbose: bool = False,
    ) -> None:
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.risk_config = risk_config or RiskConfig()
        self.verbose = verbose

        # Inject simulation clock into risk manager (or create a default one)
        if hasattr(self.risk_manager, 'set_clock'):
            pass

        # Use provided simulation config or default
        sim_cfg = simulation_config or SimulationConfig.default()
        self._sim_config = sim_cfg
        self._fee_model = FeeModel(sim_cfg)
        self._slippage_model = SlippageModel(sim_cfg)
        self._funding_model = FundingModel(sim_cfg)
        self._latency_model = LatencyModel(sim_cfg)

        # Internal simulation clock
        self._clock: SimulationClock = SimulationClock()

    # ── Internal state ────────────────────────────────────────────
    _balance: float = 0.0
    _position_side: Optional[str] = None
    _entry_price: float = 0.0
    _entry_time: float = 0.0
    _position_size: float = 0.0
    _last_funding_time: Optional[datetime] = None
    _equity_curve: List[float] = field(default_factory=list)
    _trades: List[TradeRecord] = field(default_factory=list)
    _total_funding_fees: float = 0.0

    async def run(
        self,
        service: MarketDataService,
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
        service : MarketDataService
            The centralized market data service used to fetch candles.
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
        # Fetch candles via the centralized MarketDataService
        # -----------------------------------------------------------------
        candles: List[Candle] = await service.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=since,
            start_time=start_time,
            end_time=end_time,
        )
        if len(candles) < 2:
            print("Not enough candles (<2) – returning clean empty report.")
            return PerformanceReport(
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                total_pnl=0.0,
                total_funding_fees=0.0,
                metrics={},
                trades=[],
                equity_curve=[self.initial_capital],
            )

        total_candles = len(candles)
        print(f"Candles fetched: {total_candles}")
        print(f"Replay range: {candles[0].timestamp} .. {candles[-1].timestamp}")
        print("Replay started")

        # -----------------------------------------------------------------
        # Initialise simulation clock
        # -----------------------------------------------------------------
        self._clock = SimulationClock.from_backtest_start(candles[0].timestamp)
        if hasattr(self.risk_manager, 'set_clock'):
            self.risk_manager.set_clock(self._clock)

        # -----------------------------------------------------------------
        # Initialise state
        # -----------------------------------------------------------------
        self.risk_manager.reset_all()

        self._balance = self.initial_capital
        self._equity_curve = [self._balance]
        self._trades = []
        self._total_funding_fees = 0.0

        self._position_side = None
        self._entry_price = 0.0
        self._entry_time = 0.0
        self._position_size = 0.0
        self._last_funding_time = None

        peak_equity = self._balance
        print(f"Initial capital: {self._balance:.2f}")

        # -----------------------------------------------------------------
        # Replay candles in order – deterministic replay
        # -----------------------------------------------------------------
        for i in range(total_candles):
            candle = candles[i]
            candle_time = datetime.fromtimestamp(
                candle.timestamp / 1000, tz=timezone.utc
            )

            # Advance simulation clock to candle time
            self._clock.set_time(candle_time)

            # --- Progress logging (only in verbose mode) -----------------
            if self.verbose and i > 0 and i % 5000 == 0:
                pct = 100.0 * i / total_candles
                print(f"Progress: {i}/{total_candles} ({pct:.1f}%), balance={self._balance:.2f}")

            # --- Funding simulation ---------------------------------------
            self._apply_funding(candle, candle_time)

            # --- Check stop loss / take profit for open position ----------
            close_reason: Optional[str] = None
            if self._position_side is not None:
                close_reason = self._check_stop_loss_take_profit(candle)

            # If stop loss or take profit triggered, close immediately
            if close_reason:
                await self._close_position(candle, force=False, reason=close_reason)
                # Skip signal processing for this candle
                self._record_equity(candle)
                continue

            # --- Get signal from strategy (receives Candle list) ----------
            signal = await strategy.get_signal(symbol, candles[: i + 1])

            # Print signal only if not HOLD or verbose mode
            if signal != "hold" or self.verbose:
                print(f"[SIGNAL] {signal.upper()} at candle_time={candle_time}")

            # --- Open position --------------------------------------------
            if self._position_side is None and signal in ("long", "short"):
                await self._latency_model.apply_order_latency()
                await self._open_position(signal, candle, candle_time)

            # --- Close position (signal) ----------------------------------
            elif self._position_side is not None and signal == "close":
                await self._latency_model.apply_order_latency()
                await self._close_position(candle, force=False, reason="signal")

            # --- Record equity curve --------------------------------------
            self._record_equity(candle)

            # --- Check max drawdown ---------------------------------------
            current_equity = self._equity_curve[-1]
            if current_equity > peak_equity:
                peak_equity = current_equity
            drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0.0
            if drawdown > self.risk_config.max_drawdown_pct:
                print(f"[RISK] Max drawdown {drawdown:.2%} exceeded – stopping replay.")
                if self._position_side is not None:
                    await self._close_position(candle, force=True, reason="max_drawdown")
                break

        # --- Force-close any open position at the end --------------------
        if self._position_side is not None:
            await self._close_position(candles[-1], force=True, reason="end_of_backtest")

        # --- Compute metrics & report ------------------------------------
        metrics = compute_metrics(
            initial_capital=self.initial_capital,
            final_capital=self._balance,
            equity_curve=self._equity_curve,
            trades=self._trades,
        )

        print(f"Backtest completed. Final balance={self._balance:.2f}, "
              f"PnL={self._balance - self.initial_capital:.2f}")

        return PerformanceReport(
            initial_capital=self.initial_capital,
            final_capital=self._balance,
            total_pnl=self._balance - self.initial_capital,
            total_funding_fees=self._total_funding_fees,
            metrics=metrics,
            trades=self._trades,
            equity_curve=self._equity_curve,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_funding(self, candle: Candle, timestamp: datetime) -> None:
        """Apply funding fees if a position is open."""
        if not self._funding_model.enabled or self._position_side is None:
            return

        if self._last_funding_time is None:
            self._last_funding_time = self._funding_model.next_funding_time(
                self._entry_time
            )

        while timestamp >= self._last_funding_time:
            payment = self._funding_model.apply_funding(
                position_side=self._position_side,
                quantity=self._position_size,
                price=candle.close,
            )
            self._balance -= payment
            self._total_funding_fees += payment
            if self.verbose or abs(payment) > 0.001:
                print(f"[FUNDING] payment={payment:.2f}, balance={self._balance:.2f}, time={timestamp}")
            self._last_funding_time += timedelta(hours=self._funding_model._interval_hours)

    def _compute_entry_price(self, side: str, price: float) -> float:
        """Apply slippage to entry price using the slippage model."""
        return self._slippage_model.entry_price(side, price)

    def _compute_exit_price(self, side: str, price: float) -> float:
        """Apply slippage to exit price using the slippage model."""
        return self._slippage_model.exit_price(side, price)

    async def _open_position(self, signal: str, candle: Candle, candle_time: datetime) -> None:
        """Open a new position after checking risk controls."""
        equity_before_trade = self._balance
        can_open = self.risk_manager.can_open_position(
            symbol=candle.symbol if hasattr(candle, 'symbol') else "UNKNOWN",
            side=signal,
            price=candle.close,
            current_positions_count=0,
            current_capital=equity_before_trade,
        )
        if not can_open:
            print(f"[EXECUTION] ORDER REJECTED reason=risk_blocked at time={candle_time}")
            return

        exec_price = self._compute_entry_price(signal, candle.close)
        max_capital_used = equity_before_trade * self.risk_config.max_position_size
        base_quantity, _ = self.risk_manager.calculate_position_size(
            capital=max_capital_used,
            price=exec_price,
        )
        if base_quantity <= 0:
            print(f"[EXECUTION] ORDER REJECTED reason=zero_quantity at time={candle_time}")
            return

        quantity = base_quantity * self.risk_config.max_leverage
        fee_result = self._fee_model.calculate_total_fee(
            quantity, exec_price, exec_price
        )
        commission_cost = fee_result.entry_fee
        self._balance -= commission_cost
        self._position_side = signal
        self._entry_price = exec_price
        self._entry_time = candle.timestamp
        self._position_size = quantity
        print(
            f"[EXECUTION] ORDER FILLED {signal.upper()} at {exec_price:.2f}, "
            f"size={quantity:.4f}, fee={commission_cost:.2f}, "
            f"balance={self._balance:.2f}, time={candle_time}"
        )

    async def _close_position(self, candle: Candle, force: bool = False,
                              reason: str = "signal") -> None:
        """Close the current open position."""
        exec_price = self._compute_exit_price(self._position_side, candle.close)
        close_commission = self._fee_model.calculate_exit_fee(
            self._position_size, exec_price
        )

        if self._position_side == "long":
            gross_pnl = (exec_price - self._entry_price) * self._position_size
        else:
            gross_pnl = (self._entry_price - exec_price) * self._position_size

        total_commission = self._fee_model.total_commission(
            self._position_size, self._entry_price, exec_price
        )
        net_pnl = gross_pnl - total_commission

        self._balance += net_pnl

        candle_time = datetime.fromtimestamp(
            candle.timestamp / 1000, tz=timezone.utc
        )

        self._trades.append(
            TradeRecord(
                symbol="UNKNOWN",
                side=self._position_side,
                entry_time=self._entry_time,
                exit_time=candle.timestamp,
                entry_price=self._entry_price,
                exit_price=exec_price,
                quantity=self._position_size,
                pnl=net_pnl,
                commission=total_commission,
                close_reason=reason,
            )
        )
        self.risk_manager.record_trade_pnl(net_pnl)

        tag = "FORCE CLOSE" if force else "CLOSE"
        print(
            f"[EXECUTION] {tag} {self._position_side.upper()} at {exec_price:.2f}, "
            f"PnL={net_pnl:.2f}, commission={total_commission:.2f}, "
            f"balance={self._balance:.2f}, reason={reason}, time={candle_time}"
        )

        self._position_side = None
        self._last_funding_time = None

    def _check_stop_loss_take_profit(self, candle: Candle) -> Optional[str]:
        """
        Check if stop loss or take profit is triggered.

        Returns the close reason string if triggered, else None.
        """
        if self._position_side is None:
            return None

        price = candle.close
        if self._position_side == "long":
            change = (price - self._entry_price) / self._entry_price
        else:
            change = (self._entry_price - price) / self._entry_price

        if change <= -self.risk_config.stop_loss_pct:
            print(f"[RISK] Stop loss triggered (change={change:.2%})")
            return "stop_loss"
        if change >= self.risk_config.take_profit_pct:
            print(f"[RISK] Take profit triggered (change={change:.2%})")
            return "take_profit"
        return None

    def _record_equity(self, candle: Candle) -> None:
        """Record the equity curve point."""
        if self._position_side is not None:
            if self._position_side == "long":
                unrealized_pnl = (candle.close - self._entry_price) * self._position_size
            else:
                unrealized_pnl = (self._entry_price - candle.close) * self._position_size
            self._equity_curve.append(self._balance + unrealized_pnl)
        else:
            self._equity_curve.append(self._balance)

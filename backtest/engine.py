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
import logging
from typing import Any, Dict, List, Optional

from backtest.models import TradeRecord
from backtest.metrics import compute_metrics, compute_exit_summary
from backtest.report import PerformanceReport
from market_data import MarketDataService
from market_data.models.candle import Candle
from market_structure.mtf import MultiTimeframeConfig, load_structure_feeds
from market_structure.event_log import StructureEventLogger
from risk.manager import RiskManager
from risk.exit_levels import EntryRiskHints, PositionExitState, TrailSlEvent, take_profit_r_multiple
from risk.partial_profit_log import format_partial_profit_message
from simulation.config import SimulationConfig
from simulation.fee_model import FeeModel
from simulation.slippage_model import SlippageModel
from simulation.funding_model import FundingModel
from simulation.latency_model import LatencyModel
from core.clock import SimulationClock
from utils import console as term

logger = logging.getLogger(__name__)


@dataclass
class PortfolioPosition:
    """Open position state for multi-symbol portfolio backtest."""

    symbol: str
    side: str
    entry_price: float
    entry_time: int
    position_size: float
    exit_state: PositionExitState
    last_funding_time: Optional[datetime] = None


@dataclass
class RiskConfig:
    """Risk parameters applied during backtest (sourced from AppConfig / .env)."""
    max_position_size: float = 1.0
    max_leverage: float = 5.0
    max_drawdown_pct: float = 0.20
    halt_on_drawdown: bool = False

    @classmethod
    def from_app_config(cls, config: Any) -> "RiskConfig":
        return cls(
            max_position_size=float(getattr(config, "position_size_pct", 1.0)),
            max_leverage=float(getattr(config, "max_leverage", 5)),
            max_drawdown_pct=float(getattr(config, "max_drawdown_percent", 20.0)) / 100.0,
            halt_on_drawdown=bool(getattr(config, "backtest_halt_on_drawdown", False)),
        )


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
    _exit_state: Optional[PositionExitState] = None
    _current_bar_index: int = 0
    _active_symbol: Optional[str] = None
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
        mtf_config: Optional[MultiTimeframeConfig] = None,
        structure_pivot_len: int = 5,
        structure_tolerance_bps: float = 0.0,
        structure_use_bos_choch: bool = True,
        structure_break_confirm_close: bool = True,
    ) -> PerformanceReport:
        """
        Run the backtest by replaying historical candles from MarketDataService.

        (docstring unchanged)
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
            logger.warning("Not enough candles (<2) – returning clean empty report.")
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
        logger.info("Candles fetched: %d", total_candles)
        logger.info("Replay range: %s .. %s", candles[0].timestamp, candles[-1].timestamp)
        logger.info("Replay started")

        structure_feed = None
        if mtf_config and mtf_config.is_active:
            feeds = await load_structure_feeds(
                service,
                [symbol],
                exchange,
                mtf_config,
                pivot_len=structure_pivot_len,
                tolerance_bps=structure_tolerance_bps,
                use_bos_choch=structure_use_bos_choch,
                break_confirm_close=structure_break_confirm_close,
                limit=limit,
                since=since,
                start_time=start_time,
                end_time=end_time,
            )
            structure_feed = feeds.get(symbol)
            if structure_feed:
                logger.info(
                    "[MTF] Structure filter: %s (strategy=%s)",
                    mtf_config.structure_timeframe,
                    mtf_config.strategy_timeframe,
                )

        # -----------------------------------------------------------------
        # Initialise simulation clock
        # -----------------------------------------------------------------
        self._clock = SimulationClock.from_backtest_start(candles[0].timestamp)
        if hasattr(self.risk_manager, 'set_clock'):
            self.risk_manager.set_clock(self._clock)

        # -----------------------------------------------------------------
        # Initialise state
        # -----------------------------------------------------------------
        self.risk_manager.reset_all(initial_capital=self.initial_capital)

        self._balance = self.initial_capital
        self._equity_curve = [self._balance]
        self._trades = []
        self._total_funding_fees = 0.0

        self._position_side = None
        self._entry_price = 0.0
        self._entry_time = 0.0
        self._position_size = 0.0
        self._last_funding_time = None
        self._last_hold_printed: Optional[str] = None
        self._exit_state = None
        self._current_bar_index = 0

        peak_equity = self._balance
        logger.info("Initial capital: %.2f", self._balance)

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
            self._current_bar_index = i

            # --- Progress logging (file only) -----------------------------
            if self.verbose and i > 0 and i % 5000 == 0:
                pct = 100.0 * i / total_candles
                logger.info(
                    "Progress: %d/%d (%.1f%%), balance=%.2f",
                    i, total_candles, pct, self._balance,
                )

            # --- Funding simulation ---------------------------------------
            self._apply_funding(candle, candle_time)

            # --- Global TP/SL via RiskManager --------------------------------
            if self._position_side is not None and self._exit_state is not None:
                if await self._process_risk_exits(candle, i, strategy):
                    self._record_equity(candle)
                    continue

            # --- Get signal from strategy (receives Candle list) ----------
            if structure_feed and hasattr(strategy, "set_structure_trend"):
                state = structure_feed.sync_to(candle.timestamp)
                strategy.set_structure_trend(state.effective_trend)
                if hasattr(strategy, "set_structure_state"):
                    strategy.set_structure_state(state)
            signal = await strategy.get_signal(symbol, candles[: i + 1])

            if signal == "hold":
                if self._position_side is None:
                    hold_reason = getattr(strategy, "last_hold_reason", "waiting")
                    if (
                        hold_reason != "in_trade"
                        and hold_reason != self._last_hold_printed
                    ):
                        term.hold(candle_time, hold_reason)
                        self._last_hold_printed = hold_reason
            elif signal in ("long", "short"):
                self._last_hold_printed = None
                term.signal(signal, candle_time)

            # --- Open / flip position -------------------------------------
            if signal in ("long", "short"):
                if self._position_side is None:
                    await self._latency_model.apply_order_latency()
                    await self._open_position(signal, candle, candle_time, strategy, i)
                elif signal != self._position_side:
                    await self._latency_model.apply_order_latency()
                    await self._close_position(
                        candle, force=False, reason="flip", strategy=strategy
                    )
                    await self._open_position(signal, candle, candle_time, strategy, i)

            # --- Close position (strategy trend exit etc.) ----------------
            elif self._position_side is not None and signal == "close":
                self._last_hold_printed = None
                exit_reason = getattr(strategy, "last_exit_reason", None) or "signal"
                if exit_reason == "trend_exit" and not self.risk_manager.is_trend_exit_allowed(
                    self._exit_state
                ):
                    pass
                else:
                    await self._latency_model.apply_order_latency()
                    await self._close_position(
                        candle, force=False, reason=exit_reason, strategy=strategy
                    )

            # --- Record equity curve --------------------------------------
            self._record_equity(candle)

            # --- Max drawdown halt (optional; default off – let global SL/TP exit) ---
            if self.risk_config.halt_on_drawdown:
                current_equity = self._equity_curve[-1]
                if current_equity > peak_equity:
                    peak_equity = current_equity
                drawdown = (
                    (peak_equity - current_equity) / peak_equity
                    if peak_equity > 0
                    else 0.0
                )
                if drawdown > self.risk_config.max_drawdown_pct:
                    logger.warning(
                        "Max drawdown %.2f%% exceeded – stopping replay.",
                        drawdown * 100,
                    )
                    if self._position_side is not None:
                        await self._close_position(
                            candle,
                            force=True,
                            reason="max_drawdown",
                            strategy=strategy,
                        )
                    break

        # --- Force-close any open position at the end --------------------
        if self._position_side is not None:
            await self._close_position(
                candles[-1], force=True, reason="end_of_backtest", strategy=strategy
            )

        # --- Compute metrics & report ------------------------------------
        metrics = compute_metrics(
            initial_capital=self.initial_capital,
            final_capital=self._balance,
            equity_curve=self._equity_curve,
            trades=self._trades,
        )
        exit_summary = compute_exit_summary(self._trades)

        term.backtest_summary(self._balance, self._balance - self.initial_capital)

        return PerformanceReport(
            initial_capital=self.initial_capital,
            final_capital=self._balance,
            total_pnl=self._balance - self.initial_capital,
            total_funding_fees=self._total_funding_fees,
            metrics=metrics,
            trades=self._trades,
            equity_curve=self._equity_curve,
            exit_summary=exit_summary,
        )

    async def run_portfolio(
        self,
        service: MarketDataService,
        strategies: Dict[str, Any],
        symbols: List[str],
        timeframe: str,
        exchange: str = "default",
        limit: int = 10_000,
        since: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        mtf_config: Optional[MultiTimeframeConfig] = None,
        structure_pivot_len: int = 5,
        structure_tolerance_bps: float = 0.0,
        structure_use_bos_choch: bool = True,
        structure_break_confirm_close: bool = True,
        max_concurrent_trades: Optional[int] = None,
        structure_logger: Optional[StructureEventLogger] = None,
    ) -> PerformanceReport:
        """
        Portfolio backtest: shared capital, one position slot per symbol (configurable).
        Scans all symbols each bar; opens multiple concurrent positions up to the limit.
        """
        candles_map: Dict[str, List[Candle]] = {}
        for symbol in symbols:
            candles = await service.get_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                since=since,
                start_time=start_time,
                end_time=end_time,
            )
            candles_map[symbol] = candles
            logger.info("Portfolio loaded %d candles for %s", len(candles), symbol)

        if not candles_map or any(len(c) < 2 for c in candles_map.values()):
            logger.warning("Not enough candles for portfolio backtest.")
            return PerformanceReport(
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                total_pnl=0.0,
                total_funding_fees=0.0,
                metrics={},
                trades=[],
                equity_curve=[self.initial_capital],
            )

        ts_sets = [set(c.timestamp for c in candles_map[s]) for s in symbols]
        timeline = sorted(set.intersection(*ts_sets))
        if len(timeline) < 2:
            logger.warning("No common candle timestamps across symbols.")
            return PerformanceReport(
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                total_pnl=0.0,
                total_funding_fees=0.0,
                metrics={},
                trades=[],
                equity_curve=[self.initial_capital],
            )

        structure_feeds = {}
        if mtf_config and mtf_config.is_active:
            structure_feeds = await load_structure_feeds(
                service,
                symbols,
                exchange,
                mtf_config,
                pivot_len=structure_pivot_len,
                tolerance_bps=structure_tolerance_bps,
                use_bos_choch=structure_use_bos_choch,
                break_confirm_close=structure_break_confirm_close,
                limit=limit,
                since=since,
                start_time=start_time,
                end_time=end_time,
            )
            logger.info(
                "[MTF] Portfolio structure filter: %s (strategy=%s)",
                mtf_config.structure_timeframe,
                mtf_config.strategy_timeframe,
            )

        first_ts = timeline[0]
        self._clock = SimulationClock.from_backtest_start(first_ts)
        if hasattr(self.risk_manager, "set_clock"):
            self.risk_manager.set_clock(self._clock)

        self.risk_manager.reset_all(initial_capital=self.initial_capital)
        self._balance = self.initial_capital
        self._equity_curve = [self._balance]
        self._trades = []
        self._total_funding_fees = 0.0
        self._position_side = None
        self._active_symbol = None
        self._exit_state = None
        self._last_hold_printed = None
        self._portfolio_best_near_miss = None
        self._portfolio_positions: Dict[str, PortfolioPosition] = {}

        configured_max = max_concurrent_trades
        if configured_max is None:
            if getattr(
                self.risk_manager.config, "portfolio_max_concurrent_symbols", True
            ):
                configured_max = len(symbols)
            else:
                configured_max = self.risk_manager._get_max_concurrent_trades()
        effective_max = min(configured_max, len(symbols))

        idx_map = {s: 0 for s in symbols}
        bar_index = 0

        logger.info(
            "Portfolio replay: %d symbols, %d common bars, capital=%.2f, max_concurrent=%d",
            len(symbols), len(timeline), self._balance, effective_max,
        )
        term.print_portfolio_header(symbols, self.initial_capital, max_concurrent=effective_max)

        for ts in timeline:
            candle_time = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            self._clock.set_time(candle_time)
            self._current_bar_index = bar_index

            # ── Manage open positions (each symbol independently) ────────
            for sym in list(self._portfolio_positions.keys()):
                pos = self._portfolio_positions[sym]
                strategy = strategies[sym]
                while (
                    idx_map[sym] < len(candles_map[sym])
                    and candles_map[sym][idx_map[sym]].timestamp < ts
                ):
                    idx_map[sym] += 1
                candle = candles_map[sym][idx_map[sym]]
                history = candles_map[sym][: idx_map[sym] + 1]

                feed = structure_feeds.get(sym)
                state = None
                if feed and hasattr(strategy, "set_structure_trend"):
                    state = feed.sync_to(ts)
                    strategy.set_structure_trend(state.effective_trend)
                    if hasattr(strategy, "set_structure_state"):
                        strategy.set_structure_state(state)

                self._load_portfolio_position(pos)
                self._apply_funding(candle, candle_time)

                closed = False
                if self._exit_state is not None:
                    if await self._process_risk_exits(
                        candle, bar_index, strategy=strategy
                    ):
                        closed = True

                if not closed and self._position_side is not None:
                    exit_sig = await strategy.get_exit_signal(sym, history)
                    if exit_sig == "close" and self._position_side is not None:
                        exit_reason = getattr(strategy, "last_exit_reason", None) or "signal"
                        if exit_reason == "trend_exit" and not self.risk_manager.is_trend_exit_allowed(
                            self._exit_state
                        ):
                            pass
                        else:
                            await self._close_position(
                                candle,
                                force=False,
                                reason=exit_reason,
                                strategy=strategy,
                                bar_index=bar_index,
                            )
                            closed = True

                if closed:
                    self._portfolio_positions.pop(sym, None)
                else:
                    self._save_portfolio_position(pos)

            # ── Scan flat symbols for new entries ─────────────────────────
            prospects = []
            best_near_miss: tuple[str, float] | None = None
            scan_states: Dict[str, Any] = {}
            open_count = len(self._portfolio_positions)

            for sym in symbols:
                if sym in self._portfolio_positions:
                    continue
                while (
                    idx_map[sym] < len(candles_map[sym])
                    and candles_map[sym][idx_map[sym]].timestamp < ts
                ):
                    idx_map[sym] += 1
                if candles_map[sym][idx_map[sym]].timestamp != ts:
                    continue

                history = candles_map[sym][: idx_map[sym] + 1]
                strat = strategies[sym]
                feed = structure_feeds.get(sym)
                state = None
                if feed and hasattr(strat, "set_structure_trend"):
                    state = feed.sync_to(ts)
                    strat.set_structure_trend(state.effective_trend)
                    if hasattr(strat, "set_structure_state"):
                        strat.set_structure_state(state)
                scan_states[sym] = state

                if hasattr(strat, "evaluate_prospect"):
                    prospect = await strat.evaluate_prospect(sym, history)
                    hold_reason = getattr(strat, "last_hold_reason", "waiting")
                    near_score = getattr(strat, "last_scan_score", None)
                    if structure_logger and structure_logger.enabled:
                        structure_logger.record_scan(
                            sym,
                            state,
                            candle_time,
                            hold_reason=hold_reason if not prospect else "waiting",
                            scan_score=near_score if not prospect else None,
                        )
                    if prospect:
                        prospects.append(prospect)
                    elif near_score is not None and near_score > 0:
                        if best_near_miss is None or near_score > best_near_miss[1]:
                            best_near_miss = (sym, near_score)

            if prospects and open_count < effective_max:
                prospects.sort(key=lambda p: p.score, reverse=True)
                slots_left = effective_max - open_count
                for prospect in prospects[:slots_left]:
                    sym = prospect.symbol
                    if sym in self._portfolio_positions:
                        continue
                    strategy = strategies[sym]
                    candle = candles_map[sym][idx_map[sym]]
                    strategy.last_entry_hints = prospect.hints
                    self._active_symbol = sym
                    if structure_logger and structure_logger.enabled:
                        structure_logger.record_pick(
                            sym,
                            prospect.side,
                            prospect.score,
                            scan_states.get(sym),
                            candle_time,
                            breakdown=getattr(prospect, "reasons", None),
                        )
                    term.portfolio_pick(prospect, candle_time)
                    await self._latency_model.apply_order_latency()
                    opened = await self._open_position(
                        prospect.side,
                        candle,
                        candle_time,
                        strategy,
                        bar_index,
                        current_positions_count=len(self._portfolio_positions),
                        sizing_slots=effective_max,
                    )
                    if opened and self._position_side is not None:
                        self._portfolio_positions[sym] = PortfolioPosition(
                            symbol=sym,
                            side=self._position_side,
                            entry_price=self._entry_price,
                            entry_time=int(self._entry_time),
                            position_size=self._position_size,
                            exit_state=self._exit_state,
                            last_funding_time=self._last_funding_time,
                        )
                        self._clear_engine_position_state()
            elif prospects:
                for prospect in prospects[:1]:
                    term.portfolio_pick(prospect, candle_time)
                term.execution_rejected("max_concurrent", candle_time)
            else:
                if best_near_miss is not None:
                    sym_nm, score_nm = best_near_miss
                    prev = self._portfolio_best_near_miss
                    if prev is None or score_nm > prev[1]:
                        self._portfolio_best_near_miss = best_near_miss
                if self._last_hold_printed != "scanning":
                    term.hold(candle_time, "scanning")
                    self._last_hold_printed = "scanning"

            self._record_portfolio_equity(candles_map, symbols, idx_map)
            bar_index += 1

        for sym, pos in list(self._portfolio_positions.items()):
            last_candle = candles_map[sym][-1]
            self._load_portfolio_position(pos)
            await self._close_position(
                last_candle,
                force=True,
                reason="end_of_backtest",
                strategy=strategies[sym],
            )
            self._portfolio_positions.pop(sym, None)

        metrics = compute_metrics(
            initial_capital=self.initial_capital,
            final_capital=self._balance,
            equity_curve=self._equity_curve,
            trades=self._trades,
        )
        exit_summary = compute_exit_summary(self._trades)
        term.backtest_summary(self._balance, self._balance - self.initial_capital)
        if not self._trades and self._portfolio_best_near_miss is not None:
            sym_nm, score_nm = self._portfolio_best_near_miss
            logger.warning(
                "Portfolio: 0 trades. Best near-miss %s score=%.0f (below min_signal_score?)",
                sym_nm,
                score_nm,
            )
            term.scan_near_miss(sym_nm, score_nm)

        return PerformanceReport(
            initial_capital=self.initial_capital,
            final_capital=self._balance,
            total_pnl=self._balance - self.initial_capital,
            total_funding_fees=self._total_funding_fees,
            metrics=metrics,
            trades=self._trades,
            equity_curve=self._equity_curve,
            exit_summary=exit_summary,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_portfolio_position(self, pos: PortfolioPosition) -> None:
        self._active_symbol = pos.symbol
        self._position_side = pos.side
        self._entry_price = pos.entry_price
        self._entry_time = pos.entry_time
        self._position_size = pos.position_size
        self._exit_state = pos.exit_state
        self._last_funding_time = pos.last_funding_time

    def _save_portfolio_position(self, pos: PortfolioPosition) -> None:
        pos.position_size = self._position_size
        pos.exit_state = self._exit_state
        pos.last_funding_time = self._last_funding_time

    def _clear_engine_position_state(self) -> None:
        self._position_side = None
        self._active_symbol = None
        self._entry_price = 0.0
        self._entry_time = 0.0
        self._position_size = 0.0
        self._exit_state = None
        self._last_funding_time = None

    def _record_portfolio_equity(
        self,
        candles_map: Dict[str, List[Candle]],
        symbols: List[str],
        idx_map: Dict[str, int],
    ) -> None:
        unrealized = 0.0
        for sym, pos in self._portfolio_positions.items():
            idx = idx_map[sym]
            if idx >= len(candles_map[sym]):
                continue
            close = candles_map[sym][idx].close
            if pos.side == "long":
                unrealized += (close - pos.entry_price) * pos.position_size
            else:
                unrealized += (pos.entry_price - close) * pos.position_size
        self._equity_curve.append(self._balance + unrealized)

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
                logger.debug(
                    "Funding %s payment=%.2f balance=%.2f time=%s",
                    self._position_side, payment, self._balance, timestamp,
                )
            self._last_funding_time += timedelta(hours=self._funding_model._interval_hours)

    def _compute_entry_price(self, side: str, price: float) -> float:
        """Apply slippage to entry price using the slippage model."""
        return self._slippage_model.entry_price(side, price)

    def _compute_exit_price(self, side: str, price: float) -> float:
        """Apply slippage to exit price using the slippage model."""
        return self._slippage_model.exit_price(side, price)

    async def _open_position(
        self,
        signal: str,
        candle: Candle,
        candle_time: datetime,
        strategy: Any,
        bar_index: int,
        *,
        current_positions_count: int = 0,
        sizing_slots: int = 1,
    ) -> bool:
        """Open a new position after checking risk controls. Returns True if filled."""
        equity_before_trade = self._balance
        symbol = self._active_symbol or (
            candle.symbol if hasattr(candle, "symbol") else "UNKNOWN"
        )
        can_open = self.risk_manager.can_open_position(
            symbol=symbol,
            side=signal,
            price=candle.close,
            current_positions_count=current_positions_count,
            current_capital=equity_before_trade,
        )
        if not can_open:
            term.execution_rejected("risk_blocked", candle_time)
            return False

        exec_price = self._compute_entry_price(signal, candle.close)
        hints: Optional[EntryRiskHints] = getattr(strategy, "last_entry_hints", None)
        exit_state = self.risk_manager.create_exit_state(
            signal,
            exec_price,
            hints=hints,
            entry_bar_index=bar_index,
        )
        if exit_state is None:
            term.execution_rejected("invalid_stop_loss", candle_time)
            return False

        slots = max(int(sizing_slots), 1)
        sizing_capital = self.risk_manager.get_sizing_capital(equity_before_trade)
        sizing_capital *= self.risk_config.max_position_size
        sizing_capital /= slots
        base_quantity, _ = self.risk_manager.calculate_position_size(
            capital=sizing_capital,
            price=exec_price,
            stop_loss=exit_state.stop_loss,
        )
        if base_quantity <= 0:
            term.execution_rejected("zero_quantity", candle_time)
            return False

        quantity = base_quantity
        max_notional = (equity_before_trade / slots) * self.risk_config.max_leverage
        if max_notional > 0 and exec_price > 0:
            quantity = min(quantity, max_notional / exec_price)

        effective_leverage = (
            (quantity * exec_price) / equity_before_trade
            if equity_before_trade > 0
            else 0.0
        )
        logger.info(
            "[RISK] Size qty=%.4f notional=%.2f leverage=%.2fx SL=%.2f TP=%.2f slots=%d",
            quantity,
            quantity * exec_price,
            effective_leverage,
            exit_state.stop_loss,
            exit_state.take_profit,
            slots,
        )
        fee_result = self._fee_model.calculate_total_fee(
            quantity, exec_price, exec_price
        )
        commission_cost = fee_result.entry_fee
        self._balance -= commission_cost
        self._position_side = signal
        self._entry_price = exec_price
        self._entry_time = candle.timestamp
        self._position_size = quantity
        self._exit_state = exit_state
        self._active_symbol = symbol
        strategy.on_position_opened(
            signal,
            exec_price,
            candle_index=bar_index,
            timestamp_ms=int(candle.timestamp),
        )
        term.execution_open(
            signal,
            exec_price,
            quantity,
            commission_cost,
            self._balance,
            candle_time,
            symbol=symbol,
        )
        term.execution_levels(
            signal,
            exec_price,
            exit_state.stop_loss,
            exit_state.take_profit,
            candle_time,
            tp_r=take_profit_r_multiple(exit_state),
        )
        return True

    async def _process_risk_exits(
        self,
        candle: Candle,
        bar_index: int,
        strategy: Any = None,
    ) -> bool:
        """
        Update profit milestones, optional partial close, then TP/SL.
        Returns True if the position was fully closed.
        """
        if self._position_side is None or self._exit_state is None:
            return False

        self._exit_state, trail_events = self.risk_manager.update_exit_milestones(
            self._exit_state,
            candle.close,
            symbol=self._active_symbol or "",
        )
        for event in trail_events:
            term.trail_sl(
                self._active_symbol or "",
                self._position_side,
                event,
                datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc),
            )

        partial_frac = self.risk_manager.partial_profit_size_pct(
            self._exit_state, candle.close
        )
        if partial_frac is not None and partial_frac > 0:
            await self._partial_close_position(
                candle, partial_frac, bar_index=bar_index, strategy=strategy
            )
            self._exit_state = self.risk_manager.mark_partial_profit_taken(
                self._exit_state
            )

        close_reason = self.risk_manager.check_position_exit(
            self._exit_state, candle.close, bar_index
        )
        if close_reason:
            self._last_hold_printed = None
            await self._close_position(
                candle, force=False, reason=close_reason, strategy=strategy, bar_index=bar_index
            )
            return True
        return False

    async def _partial_close_position(
        self,
        candle: Candle,
        fraction: float,
        *,
        bar_index: Optional[int] = None,
        strategy: Any = None,
    ) -> None:
        """Close *fraction* of the open position to lock in profit at +R."""
        if (
            fraction <= 0
            or self._position_size <= 0
            or self._position_side is None
            or self._exit_state is None
        ):
            return

        total_qty_before = self._position_size
        close_qty = self._position_size * min(fraction, 1.0)
        if close_qty <= 0:
            return

        exec_price = self._compute_exit_price(self._position_side, candle.close)

        if self._position_side == "long":
            gross_pnl = (exec_price - self._entry_price) * close_qty
        else:
            gross_pnl = (self._entry_price - exec_price) * close_qty

        total_commission = self._fee_model.total_commission(
            close_qty, self._entry_price, exec_price
        )
        net_pnl = gross_pnl - total_commission
        self._balance += net_pnl

        candle_time = datetime.fromtimestamp(
            candle.timestamp / 1000, tz=timezone.utc
        )

        pct = fraction * 100.0
        symbol = self._active_symbol or "UNKNOWN"
        trigger_r = getattr(
            self.risk_manager.config, "partial_profit_at_r", 1.0
        )

        self._trades.append(
            TradeRecord(
                symbol=symbol,
                side=self._position_side,
                entry_time=self._entry_time,
                exit_time=candle.timestamp,
                entry_price=self._entry_price,
                exit_price=exec_price,
                quantity=close_qty,
                pnl=net_pnl,
                commission=total_commission,
                close_reason="partial_profit",
            )
        )
        self.risk_manager.record_trade_pnl(net_pnl)

        self._position_size -= close_qty
        remaining_qty = self._position_size

        verbose_msg = format_partial_profit_message(
            symbol=symbol,
            state=self._exit_state,
            exec_price=exec_price,
            close_pct=pct,
            close_qty=close_qty,
            total_qty_before=total_qty_before,
            net_pnl=net_pnl,
            commission=total_commission,
            remaining_qty=remaining_qty,
            trigger_r=float(trigger_r),
        )
        logger.info(verbose_msg)

        tp_r = take_profit_r_multiple(self._exit_state)
        term.partial_profit(
            self._position_side,
            pct,
            exec_price,
            net_pnl,
            remaining_qty,
            candle_time,
            symbol=symbol,
            entry=self._entry_price,
            sl_breakeven=self._exit_state.stop_loss,
            tp_runner=self._exit_state.take_profit,
            tp_r=tp_r,
            trigger_r=float(trigger_r),
        )

    async def _close_position(
        self,
        candle: Candle,
        force: bool = False,
        reason: str = "signal",
        strategy: Any = None,
        bar_index: Optional[int] = None,
    ) -> None:
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
                symbol=self._active_symbol or "UNKNOWN",
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

        if strategy is not None:
            idx = bar_index if bar_index is not None else self._current_bar_index
            strategy.on_position_closed(reason, candle_index=idx)

        term.exit_trade(
            self._position_side,
            reason,
            exec_price,
            net_pnl,
            total_commission,
            self._balance,
            candle_time,
            forced=force,
        )

        self._position_side = None
        self._active_symbol = None
        self._last_funding_time = None
        self._last_hold_printed = None
        self._exit_state = None

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

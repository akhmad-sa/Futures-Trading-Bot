"""
Professional risk management module.

Features:
- Global TP/SL (ATR, percent, or swing-anchor modes)
- Fixed-percentage risk with optional compounding on portfolio equity
- Martingale position scaling after consecutive losses
- Dynamic position sizing
- Max drawdown protection
- Daily loss limit
- Consecutive loss cooldown
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.clock import SimulationClock
from risk.exit_levels import (
    EntryRiskHints,
    PositionExitState,
    TrailSlEvent,
    check_exit,
    create_exit_state,
    should_take_partial_profit,
    update_milestones,
)
from risk.trail_sl_log import format_trail_sl_message

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """Configuration for risk manager. Can be initialised from AppConfig or directly."""

    max_daily_loss: float = 500.0
    risk_per_trade: float = 0.02
    cooldown_seconds: int = 60
    max_concurrent_trades: int = 1
    max_drawdown_percent: float = 20.0
    consecutive_loss_limit: int = 3
    max_risk_per_symbol: float = 0.1
    max_leverage: int = 5

    stop_loss_atr_multiplier: float = 2.0
    stop_loss_mode: str = "atr"
    stop_loss_pct: float = 0.015
    take_profit_rr: float = 3.0
    min_sl_pct: float = 0.005
    max_sl_pct: float = 0.018
    min_sl_hold_bars: int = 2
    move_sl_to_breakeven_at_1r: bool = True

    compounding_enabled: bool = True
    position_size_pct: float = 1.0

    martingale_enabled: bool = False
    martingale_multiplier: float = 2.0
    martingale_max_steps: int = 3


class RiskManager:
    """Central risk manager enforcing trading rules and global exits."""

    def __init__(self, config, clock: Optional[SimulationClock] = None) -> None:
        self.config = config
        self._clock: SimulationClock = clock if clock is not None else SimulationClock()
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._cumulative_pnl = 0.0
        self._peak_equity = 0.0
        self._initial_capital = 0.0
        self._consecutive_losses = 0
        self._martingale_step = 0
        self._last_trade_time: Optional[datetime] = None

    @property
    def daily_loss(self) -> float:
        return self._daily_loss

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    @property
    def martingale_step(self) -> int:
        return self._martingale_step

    def set_clock(self, clock: SimulationClock) -> None:
        self._clock = clock

    def get_sizing_capital(self, current_equity: float) -> float:
        """Capital base for position sizing (compounding uses live equity)."""
        if self._get_compounding_enabled():
            base = current_equity
        else:
            base = self._initial_capital if self._initial_capital > 0 else current_equity
        return max(base * self._get_position_size_pct(), 0.0)

    def get_martingale_multiplier(self) -> float:
        if not self._get_martingale_enabled():
            return 1.0
        return self._get_martingale_base_multiplier() ** self._martingale_step

    def create_exit_state(
        self,
        side: str,
        entry_price: float,
        *,
        hints: Optional[EntryRiskHints] = None,
        entry_bar_index: int = 0,
    ) -> Optional[PositionExitState]:
        state = create_exit_state(
            side,
            entry_price,
            hints=hints,
            entry_bar_index=entry_bar_index,
            atr_multiplier=self._get_stop_loss_atr_multiplier(),
            min_sl_pct=self._get_min_sl_pct(),
            max_sl_pct=self._get_max_sl_pct(),
            stop_loss_pct=self._get_stop_loss_pct(),
            stop_loss_mode=self._get_stop_loss_mode(),
            risk_reward=self._get_take_profit_rr(),
        )
        if state:
            tp_r = (
                (state.take_profit - entry_price) / (entry_price - state.stop_loss)
                if side == "long" and entry_price > state.stop_loss
                else (entry_price - state.take_profit) / (state.stop_loss - entry_price)
                if side == "short" and state.stop_loss > entry_price
                else self._get_take_profit_rr()
            )
            logger.info(
                "[RISK] Exit levels %s entry=%.4f SL=%.4f (1R) TP=%.4f (%.0fR runner) "
                "partial@+%.1fR=%s stepped_trail=%s (offset=%.0f)",
                side.upper(),
                entry_price,
                state.stop_loss,
                state.take_profit,
                tp_r,
                self._get_partial_profit_at_r(),
                f"{self._get_partial_profit_pct():.0f}%"
                if self._get_partial_profit_enabled()
                else "off",
                "on" if self._get_stepped_trail_enabled() else "off",
                self._get_stepped_trail_lock_offset(),
            )
        return state

    def update_breakeven(
        self, state: PositionExitState, close: float, *, symbol: str = ""
    ) -> PositionExitState:
        state, _ = self.update_exit_milestones(state, close, symbol=symbol)
        return state

    def update_exit_milestones(
        self,
        state: PositionExitState,
        close: float,
        *,
        symbol: str = "",
    ) -> tuple[PositionExitState, list[TrailSlEvent]]:
        stepped = self._get_stepped_trail_enabled()
        state, events = update_milestones(
            state,
            close,
            breakeven_enabled=(
                self._get_move_sl_to_breakeven_at_1r() and not stepped
            ),
            stepped_trail_enabled=stepped,
            stepped_trail_lock_offset=self._get_stepped_trail_lock_offset(),
        )
        for event in events:
            msg = format_trail_sl_message(
                symbol=symbol or "?",
                state=state,
                event=event,
            )
            logger.info(msg)
        return state, events

    def partial_profit_size_pct(self, state: PositionExitState, close: float) -> Optional[float]:
        """
        Return fraction of position to close (0–1) when partial profit triggers, else None.
        """
        if not should_take_partial_profit(
            state,
            close,
            enabled=self._get_partial_profit_enabled(),
            at_r=self._get_partial_profit_at_r(),
            pct=self._get_partial_profit_pct(),
        ):
            return None
        return min(max(self._get_partial_profit_pct() / 100.0, 0.0), 1.0)

    def mark_partial_profit_taken(self, state: PositionExitState) -> PositionExitState:
        state.partial_profit_taken = True
        return state

    def is_trend_exit_allowed(self, state: Optional[PositionExitState]) -> bool:
        if not getattr(self.config, "use_trend_exit", False):
            return False
        if self._get_trend_exit_after_1r_only():
            return state is not None and state.reached_1r
        return True

    def check_position_exit(
        self,
        state: PositionExitState,
        close: float,
        current_bar_index: int,
    ) -> Optional[str]:
        bars_held = max(current_bar_index - state.entry_bar_index, 0)
        return check_exit(
            state,
            close,
            bars_held,
            min_sl_hold_bars=self._get_min_sl_hold_bars(),
        )

    def can_open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        current_positions_count: int = 0,
        current_capital: float = 1000.0,
    ) -> bool:
        now = self._clock.now()
        reason = None

        if self._daily_loss >= self._get_max_daily_loss():
            reason = "daily loss limit"
            logger.info("[RISK] BLOCKED reason=%s", reason)
            return False

        if self._consecutive_losses >= self._get_consecutive_loss_limit():
            reason = "consecutive loss limit"
            if self._last_trade_time is not None:
                elapsed = (now - self._last_trade_time).total_seconds()
                if elapsed < self._get_cooldown_seconds():
                    reason = f"cooldown ({elapsed:.0f}s < {self._get_cooldown_seconds()}s)"
                    logger.info("[RISK] BLOCKED reason=%s", reason)
                    return False
            else:
                logger.info("[RISK] BLOCKED reason=%s", reason)
                return False

        if current_positions_count >= self._get_max_concurrent_trades():
            reason = "max concurrent trades"
            logger.info("[RISK] BLOCKED reason=%s", reason)
            return False

        if current_capital > self._peak_equity:
            self._peak_equity = current_capital

        if self._peak_equity > 0:
            drawdown_percent = (
                (self._peak_equity - current_capital) / self._peak_equity * 100
            )
            if drawdown_percent >= self._get_max_drawdown_percent():
                reason = f"max drawdown {drawdown_percent:.1f}%"
                logger.info("[RISK] BLOCKED reason=%s", reason)
                return False

        if self._get_martingale_enabled() and self._martingale_step >= self._get_martingale_max_steps():
            logger.info(
                "[RISK] ALLOWED symbol=%s side=%s martingale_step=%d (max)",
                symbol,
                side,
                self._martingale_step,
            )
        else:
            logger.info("[RISK] ALLOWED symbol=%s side=%s", symbol, side)
        return True

    def calculate_position_size(
        self,
        capital: float,
        price: float,
        stop_loss: Optional[float] = None,
        atr_value: Optional[float] = None,
    ) -> tuple[float, Optional[float]]:
        """
        Compute quantity from risk-per-trade, optional stop distance,
        martingale multiplier, and compounding capital.
        """
        risk_amount = capital * self._get_risk_per_trade() * self.get_martingale_multiplier()

        if stop_loss is not None:
            risk_per_unit = abs(price - stop_loss)
            min_distance = price * self._get_min_sl_pct()
            risk_per_unit = max(risk_per_unit, min_distance)
            quantity = risk_amount / risk_per_unit if risk_per_unit > 0 else 0.0
        elif atr_value is not None:
            sl_distance = atr_value * self._get_stop_loss_atr_multiplier()
            quantity = risk_amount / sl_distance if sl_distance > 0 else 0.0
            stop_loss = price - sl_distance if price > 0 else price
        else:
            quantity = risk_amount / price if price > 0 else 0.0

        max_leverage = self._get_max_leverage()
        if max_leverage > 0 and capital > 0:
            leverage = (quantity * price) / capital
            if leverage > max_leverage:
                quantity = (max_leverage * capital) / price
                logger.info(
                    "[RISK] Position size reduced to respect max leverage (%.0fx)",
                    max_leverage,
                )

        if self._get_martingale_enabled() and self._martingale_step > 0:
            logger.info(
                "[RISK] Martingale step=%d multiplier=%.2f risk_amount=%.2f",
                self._martingale_step,
                self.get_martingale_multiplier(),
                risk_amount,
            )

        return max(quantity, 0.0), stop_loss

    def record_trade_pnl(self, pnl: float) -> None:
        now = self._clock.now()
        self._daily_loss += pnl
        self._cumulative_pnl += pnl
        equity = self._peak_equity + self._cumulative_pnl
        if equity > self._peak_equity:
            self._peak_equity = equity

        if pnl < 0:
            self._consecutive_losses += 1
            self._last_trade_time = now
            if self._get_martingale_enabled():
                cap = self._get_martingale_max_steps()
                self._martingale_step = min(self._martingale_step + 1, cap)
        else:
            self._consecutive_losses = 0
            self._martingale_step = 0

        logger.info(
            "[RISK] Trade PnL recorded: %.2f, cumulative=%.2f, drawdown_peak=%.2f, "
            "martingale_step=%d",
            pnl,
            self._cumulative_pnl,
            self._peak_equity,
            self._martingale_step,
        )

    def update_daily_loss(self, loss: float) -> None:
        self.record_trade_pnl(loss)

    def reset_daily(self) -> None:
        self._daily_loss = 0.0
        self._daily_trades = 0

    def reset_all(self, initial_capital: float = 0.0) -> None:
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._cumulative_pnl = 0.0
        self._initial_capital = initial_capital
        self._peak_equity = initial_capital
        self._consecutive_losses = 0
        self._martingale_step = 0
        self._last_trade_time = None

    def _get_max_daily_loss(self) -> float:
        return getattr(self.config, "max_daily_loss", 500.0)

    def _get_risk_per_trade(self) -> float:
        return getattr(self.config, "risk_per_trade", 0.02)

    def _get_cooldown_seconds(self) -> int:
        return getattr(self.config, "cooldown_seconds", 60)

    def _get_max_concurrent_trades(self) -> int:
        return getattr(self.config, "max_concurrent_trades", 1)

    def _get_max_drawdown_percent(self) -> float:
        return getattr(self.config, "max_drawdown_percent", 20.0)

    def _get_consecutive_loss_limit(self) -> int:
        return getattr(self.config, "consecutive_loss_limit", 3)

    def _get_max_risk_per_symbol(self) -> float:
        return getattr(self.config, "max_risk_per_symbol", 0.1)

    def _get_max_leverage(self) -> int:
        return getattr(self.config, "max_leverage", 5)

    def _get_stop_loss_atr_multiplier(self) -> float:
        return getattr(self.config, "stop_loss_atr_multiplier", 2.0)

    def _get_stop_loss_mode(self) -> str:
        return getattr(self.config, "stop_loss_mode", "atr")

    def _get_stop_loss_pct(self) -> float:
        return getattr(self.config, "stop_loss_pct", 0.015)

    def _get_take_profit_rr(self) -> float:
        return getattr(self.config, "take_profit_rr", 3.0)

    def _get_min_sl_pct(self) -> float:
        return getattr(self.config, "min_sl_pct", 0.005)

    def _get_max_sl_pct(self) -> float:
        return getattr(self.config, "max_sl_pct", 0.018)

    def _get_min_sl_hold_bars(self) -> int:
        return getattr(self.config, "min_sl_hold_bars", 2)

    def _get_move_sl_to_breakeven_at_1r(self) -> bool:
        return getattr(self.config, "move_sl_to_breakeven_at_1r", True)

    def _get_trend_exit_after_1r_only(self) -> bool:
        return getattr(self.config, "trend_exit_after_1r_only", True)

    def _get_partial_profit_enabled(self) -> bool:
        return getattr(self.config, "partial_profit_enabled", False)

    def _get_partial_profit_pct(self) -> float:
        return getattr(self.config, "partial_profit_pct", 50.0)

    def _get_partial_profit_at_r(self) -> float:
        return getattr(self.config, "partial_profit_at_r", 1.0)

    def _get_stepped_trail_enabled(self) -> bool:
        return getattr(self.config, "stepped_trail_enabled", True)

    def _get_stepped_trail_lock_offset(self) -> float:
        return getattr(self.config, "stepped_trail_lock_offset", 2.0)

    def _get_compounding_enabled(self) -> bool:
        return getattr(self.config, "compounding_enabled", True)

    def _get_position_size_pct(self) -> float:
        return getattr(self.config, "position_size_pct", 1.0)

    def _get_martingale_enabled(self) -> bool:
        return getattr(self.config, "martingale_enabled", False)

    def _get_martingale_base_multiplier(self) -> float:
        return getattr(self.config, "martingale_multiplier", 2.0)

    def _get_martingale_max_steps(self) -> int:
        return getattr(self.config, "martingale_max_steps", 3)

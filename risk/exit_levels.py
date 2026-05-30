"""
Global stop-loss / take-profit computation and exit checks.

Used by RiskManager; strategies supply optional entry hints (swing anchor, ATR)
but do not own TP/SL logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TrailSlEvent:
    """One stepped trailing-SL ratchet."""

    milestone_r: float
    lock_r: float
    new_sl: float
    prev_sl: float


@dataclass
class EntryRiskHints:
    """Optional context from a strategy at entry time."""

    stop_anchor: Optional[float] = None
    atr_value: Optional[float] = None


@dataclass
class PositionExitState:
    """Active position exit levels managed by RiskManager."""

    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    initial_risk: float
    entry_bar_index: int = 0
    reached_1r: bool = False
    partial_profit_taken: bool = False
    trail_milestone_r: float = 0.0


def compute_stop_loss(
    side: str,
    entry_price: float,
    *,
    stop_anchor: Optional[float],
    atr_value: Optional[float],
    atr_multiplier: float,
    min_sl_pct: float,
    max_sl_pct: float,
    stop_loss_pct: float,
    stop_loss_mode: str,
) -> Optional[float]:
    """Compute stop-loss price from global risk settings."""
    if side == "long":
        swing = stop_anchor if stop_anchor is not None else entry_price * (1 - min_sl_pct)
        sl = swing
        if stop_loss_mode == "atr" and atr_value is not None and atr_value > 0:
            sl = min(swing, entry_price - atr_value * atr_multiplier)
        elif stop_loss_mode == "percent":
            sl = entry_price * (1 - stop_loss_pct)
        sl = min(sl, entry_price * (1 - min_sl_pct))
        sl = max(sl, entry_price * (1 - max_sl_pct))
        risk = entry_price - sl
        floor_risk = entry_price * min_sl_pct
        if risk < floor_risk:
            sl = entry_price - floor_risk
            risk = floor_risk
    else:
        swing = stop_anchor if stop_anchor is not None else entry_price * (1 + min_sl_pct)
        sl = swing
        if stop_loss_mode == "atr" and atr_value is not None and atr_value > 0:
            sl = max(swing, entry_price + atr_value * atr_multiplier)
        elif stop_loss_mode == "percent":
            sl = entry_price * (1 + stop_loss_pct)
        sl = max(sl, entry_price * (1 + min_sl_pct))
        sl = min(sl, entry_price * (1 + max_sl_pct))
        risk = sl - entry_price
        floor_risk = entry_price * min_sl_pct
        if risk < floor_risk:
            sl = entry_price + floor_risk
            risk = floor_risk

    return sl if risk > 0 else None


def compute_take_profit(
    side: str,
    entry_price: float,
    stop_loss: float,
    risk_reward: float,
) -> float:
    risk = (entry_price - stop_loss) if side == "long" else (stop_loss - entry_price)
    if side == "long":
        return entry_price + risk * risk_reward
    return entry_price - risk * risk_reward


def create_exit_state(
    side: str,
    entry_price: float,
    *,
    hints: Optional[EntryRiskHints],
    entry_bar_index: int,
    atr_multiplier: float,
    min_sl_pct: float,
    max_sl_pct: float,
    stop_loss_pct: float,
    stop_loss_mode: str,
    risk_reward: float,
) -> Optional[PositionExitState]:
    hints = hints or EntryRiskHints()
    sl = compute_stop_loss(
        side,
        entry_price,
        stop_anchor=hints.stop_anchor,
        atr_value=hints.atr_value,
        atr_multiplier=atr_multiplier,
        min_sl_pct=min_sl_pct,
        max_sl_pct=max_sl_pct,
        stop_loss_pct=stop_loss_pct,
        stop_loss_mode=stop_loss_mode,
    )
    if sl is None:
        return None
    risk = (entry_price - sl) if side == "long" else (sl - entry_price)
    tp = compute_take_profit(side, entry_price, sl, risk_reward)
    return PositionExitState(
        side=side,
        entry_price=entry_price,
        stop_loss=sl,
        take_profit=tp,
        initial_risk=risk,
        entry_bar_index=entry_bar_index,
    )


def price_at_r(state: PositionExitState, r: float) -> float:
    """Target price at *r* multiples of initial risk from entry."""
    if state.side == "long":
        return state.entry_price + state.initial_risk * r
    return state.entry_price - state.initial_risk * r


def has_reached_r(state: PositionExitState, close: float, r: float) -> bool:
    if state.initial_risk <= 0 or r <= 0:
        return False
    if state.side == "long":
        return close >= price_at_r(state, r)
    return close <= price_at_r(state, r)


def current_r_multiple(state: PositionExitState, close: float) -> float:
    """Unrealized profit in R multiples at *close*."""
    if state.initial_risk <= 0:
        return 0.0
    if state.side == "long":
        return (close - state.entry_price) / state.initial_risk
    return (state.entry_price - close) / state.initial_risk


def take_profit_r_multiple(state: PositionExitState) -> float:
    """Configured TP distance in R from entry."""
    if state.initial_risk <= 0:
        return 0.0
    if state.side == "long":
        return (state.take_profit - state.entry_price) / state.initial_risk
    return (state.entry_price - state.take_profit) / state.initial_risk


def lock_r_for_milestone(milestone_r: float, lock_offset: float) -> float:
    """
    R-level to lock SL at when price reaches *milestone_r*.

    Examples (offset=2): 1R→0R (BE), 2R→0R, 3R→1R, 4R→2R, …
    """
    return max(0.0, milestone_r - lock_offset)


def apply_stepped_trailing_sl(
    state: PositionExitState,
    close: float,
    *,
    enabled: bool,
    lock_offset: float = 2.0,
) -> tuple[PositionExitState, list[TrailSlEvent]]:
    """
    Ratchet stop-loss at each whole-R milestone for the runner.

    Long: SL only moves up. Short: SL only moves down.
    """
    events: list[TrailSlEvent] = []
    if not enabled or state.initial_risk <= 0:
        return state, events

    current_r = current_r_multiple(state, close)
    highest_m = int(current_r)
    if highest_m < 1:
        return state, events

    for m in range(1, highest_m + 1):
        if m <= int(state.trail_milestone_r):
            continue

        lock_r = lock_r_for_milestone(float(m), lock_offset)
        new_sl = (
            state.entry_price if lock_r == 0.0 else price_at_r(state, lock_r)
        )
        prev_sl = state.stop_loss
        moved = False

        if state.side == "long":
            if new_sl > state.stop_loss:
                state.stop_loss = new_sl
                moved = True
        elif new_sl < state.stop_loss:
            state.stop_loss = new_sl
            moved = True

        state.trail_milestone_r = float(m)
        if m >= 1:
            state.reached_1r = True

        if moved:
            events.append(
                TrailSlEvent(
                    milestone_r=float(m),
                    lock_r=lock_r,
                    new_sl=state.stop_loss,
                    prev_sl=prev_sl,
                )
            )

    return state, events


def update_milestones(
    state: PositionExitState,
    close: float,
    *,
    breakeven_enabled: bool,
    stepped_trail_enabled: bool = False,
    stepped_trail_lock_offset: float = 2.0,
) -> tuple[PositionExitState, list[TrailSlEvent]]:
    """Update +1R flag and apply breakeven or stepped trailing SL."""
    events: list[TrailSlEvent] = []
    if stepped_trail_enabled:
        state, events = apply_stepped_trailing_sl(
            state,
            close,
            enabled=True,
            lock_offset=stepped_trail_lock_offset,
        )
    elif breakeven_enabled:
        state = maybe_trail_breakeven(state, close, enabled=True)

    if not state.reached_1r and has_reached_r(state, close, 1.0):
        state.reached_1r = True
    return state, events


def should_take_partial_profit(
    state: PositionExitState,
    close: float,
    *,
    enabled: bool,
    at_r: float,
    pct: float,
) -> bool:
    if not enabled or state.partial_profit_taken or pct <= 0:
        return False
    return has_reached_r(state, close, at_r)


def maybe_trail_breakeven(
    state: PositionExitState,
    close: float,
    *,
    enabled: bool,
) -> PositionExitState:
    if not enabled or state.initial_risk <= 0:
        return state
    if state.side == "long":
        if close >= state.entry_price + state.initial_risk:
            state.stop_loss = max(state.stop_loss, state.entry_price)
    elif close <= state.entry_price - state.initial_risk:
        state.stop_loss = min(state.stop_loss, state.entry_price)
    return state


def check_exit(
    state: PositionExitState,
    close: float,
    bars_held: int,
    *,
    min_sl_hold_bars: int,
) -> Optional[str]:
    if state.side == "long":
        if close >= state.take_profit:
            return "take_profit"
        if bars_held >= min_sl_hold_bars and close <= state.stop_loss:
            return "stop_loss"
        if (
            bars_held < min_sl_hold_bars
            and state.initial_risk > 0
            and close <= state.entry_price - 2 * state.initial_risk
        ):
            return "stop_loss"
    else:
        if close <= state.take_profit:
            return "take_profit"
        if bars_held >= min_sl_hold_bars and close >= state.stop_loss:
            return "stop_loss"
        if (
            bars_held < min_sl_hold_bars
            and state.initial_risk > 0
            and close >= state.entry_price + 2 * state.initial_risk
        ):
            return "stop_loss"
    return None

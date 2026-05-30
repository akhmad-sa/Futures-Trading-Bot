"""Verbose logging for stepped trailing stop-loss."""

from __future__ import annotations

from risk.exit_levels import PositionExitState, TrailSlEvent


def format_trail_sl_message(
    *,
    symbol: str,
    state: PositionExitState,
    event: TrailSlEvent,
) -> str:
    lock_label = "breakeven (0R)" if event.lock_r == 0 else f"+{event.lock_r:.0f}R"
    return (
        f"[TRAIL-SL] {symbol} {state.side.upper()} milestone +{event.milestone_r:.0f}R → "
        f"SL locked at {lock_label} price={event.new_sl:.4f} "
        f"(prev SL={event.prev_sl:.4f})"
    )

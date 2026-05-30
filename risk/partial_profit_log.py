"""Verbose logging helpers for partial profit events."""

from __future__ import annotations

from risk.exit_levels import PositionExitState, current_r_multiple, take_profit_r_multiple


def format_partial_profit_message(
    *,
    symbol: str,
    state: PositionExitState,
    exec_price: float,
    close_pct: float,
    close_qty: float,
    total_qty_before: float,
    net_pnl: float,
    commission: float,
    remaining_qty: float,
    trigger_r: float,
) -> str:
    r_now = current_r_multiple(state, exec_price)
    tp_r = take_profit_r_multiple(state)
    remaining_pct = (
        (remaining_qty / total_qty_before * 100.0) if total_qty_before > 0 else 0.0
    )
    return (
        f"[PARTIAL-PROFIT] {symbol} {state.side.upper()} triggered at +{trigger_r:.1f}R "
        f"(price={exec_price:.4f}, unrealized={r_now:+.2f}R) | "
        f"closed {close_pct:.0f}% qty={close_qty:.4f}/{total_qty_before:.4f} "
        f"entry={state.entry_price:.4f} PnL={net_pnl:+.2f} fee={commission:.2f} | "
        f"SL→breakeven {state.stop_loss:.4f} | "
        f"runner TP={state.take_profit:.4f} ({tp_r:.0f}R) "
        f"remaining={remaining_qty:.4f} ({remaining_pct:.0f}% runner)"
    )

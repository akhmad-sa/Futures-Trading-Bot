"""
Human-readable Telegram messages for live trading events.
"""

from __future__ import annotations

from typing import Any


def format_score_detail(reasons: dict[str, Any] | None) -> str:
    if not reasons:
        return ""
    from strategy.signal_quality import format_breakdown

    return format_breakdown(reasons)


def format_pick(
    symbol: str,
    side: str,
    score: float,
    *,
    detail: str = "",
) -> str:
    lines = [f"🎯 PICK {symbol} {side.upper()} · score={score:.0f}"]
    if detail:
        lines.append(f"  {detail}")
    return "\n".join(lines)


def format_rejected(symbol: str | None, reason: str) -> str:
    sym = f"{symbol} " if symbol else ""
    return f"⛔ REJECTED {sym}{reason}"


def format_near_miss(symbol: str, score: float) -> str:
    return f"📊 Near-miss {symbol} · score={score:.0f} (below threshold)"


def format_open(
    symbol: str,
    side: str,
    size: float,
    price: float,
    stop_loss: float,
    take_profit: float,
    *,
    tp_r: float | None = None,
) -> str:
    risk = (price - stop_loss) if side == "long" else (stop_loss - price)
    reward = (take_profit - price) if side == "long" else (price - take_profit)
    rr = (reward / risk) if risk > 0 else 0.0
    tp_label = f"{tp_r:.0f}R" if tp_r is not None and tp_r > 1 else f"R:R={rr:.1f}"
    return (
        f"📈 OPEN {symbol} {side.upper()}\n"
        f"size {size:.4f} @ {price:.2f}\n"
        f"SL {stop_loss:.4f} · TP {take_profit:.4f} ({tp_label})"
    )


def format_partial(
    symbol: str,
    side: str,
    pct: float,
    price: float,
    pnl: float,
    *,
    trigger_r: float = 1.0,
) -> str:
    emoji = "🟢" if pnl >= 0 else "🔴"
    return (
        f"{emoji} PARTIAL {symbol} {side.upper()} +{trigger_r:.0f}R\n"
        f"closed {pct:.0f}% @ {price:.4f} · PnL {pnl:+.2f}"
    )


def format_exit(symbol: str, side: str, pnl: float, *, reason: str = "") -> str:
    emoji = "🟢" if pnl >= 0 else "🔴"
    suffix = f" ({reason})" if reason else ""
    return f"{emoji} EXIT {symbol} {side.upper()}{suffix}\nPnL {pnl:+.2f}"

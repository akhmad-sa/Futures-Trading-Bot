"""
User-facing terminal output (stdout).

Verbose diagnostics go to the log file via ``logging``; this module is for
the minimal live/backtest console stream only.
"""

from __future__ import annotations

from datetime import datetime


def _ts(candle_time: datetime) -> str:
    return candle_time.strftime("%Y-%m-%d %H:%M:%S")


def hold(candle_time: datetime, reason: str = "waiting") -> None:
    print(f"[HOLD] {reason} | {_ts(candle_time)}", flush=True)


def signal(side: str, candle_time: datetime) -> None:
    label = side.upper()
    print(f"[SIGNAL] {label} | {_ts(candle_time)}", flush=True)


def execution_open(
    side: str,
    price: float,
    size: float,
    fee: float,
    balance: float,
    candle_time: datetime,
    *,
    symbol: str = "",
) -> None:
    label = "LONG" if side == "long" else "SHORT"
    sym = f"{symbol} " if symbol else ""
    print(
        f"[EXECUTION] OPEN {sym}{label} at {price:.2f}, "
        f"size={size:.4f}, fee={fee:.2f}, balance={balance:.2f} | {_ts(candle_time)}",
        flush=True,
    )


def execution_rejected(reason: str, candle_time: datetime) -> None:
    print(f"[EXECUTION] REJECTED reason={reason} | {_ts(candle_time)}", flush=True)


def partial_profit(
    side: str,
    pct: float,
    price: float,
    pnl: float,
    remaining_size: float,
    candle_time: datetime,
    *,
    symbol: str = "",
    entry: float = 0.0,
    sl_breakeven: float = 0.0,
    tp_runner: float = 0.0,
    tp_r: float = 0.0,
    trigger_r: float = 1.0,
) -> None:
    label = "LONG" if side == "long" else "SHORT"
    sym = f"{symbol} " if symbol else ""
    print(
        f"[PARTIAL] {sym}{label} +{trigger_r:.0f}R | closed {pct:.0f}% at {price:.4f}, "
        f"PnL={pnl:+.2f}, SL→BE {sl_breakeven:.4f}, "
        f"runner TP={tp_runner:.4f} ({tp_r:.0f}R), remaining={remaining_size:.4f} | "
        f"{_ts(candle_time)}",
        flush=True,
    )


def exit_trade(
    side: str,
    reason: str,
    price: float,
    pnl: float,
    commission: float,
    balance: float,
    candle_time: datetime,
    *,
    forced: bool = False,
) -> None:
    label = "LONG" if side == "long" else "SHORT"
    tag = "FORCE EXIT" if forced else "EXIT"
    print(
        f"[{tag}] {label} {reason} at {price:.2f}, "
        f"PnL={pnl:.2f}, commission={commission:.2f}, balance={balance:.2f} | {_ts(candle_time)}",
        flush=True,
    )


def backtest_summary(final_balance: float, pnl: float) -> None:
    print(f"Backtest completed. Final balance={final_balance:.2f}, PnL={pnl:.2f}", flush=True)


def print_live_header(
    mode: str,
    symbols: list,
    capital: float,
    timeframe: str,
    structure_timeframe: str | None,
    *,
    max_concurrent: int = 1,
) -> None:
    label = "PAPER TRADE" if mode == "papertrade" else "LIVE"
    mtf = (
        f"strategy={timeframe} structure={structure_timeframe}"
        if structure_timeframe
        else f"timeframe={timeframe}"
    )
    print(f"\n=== {label} PORTFOLIO ===", flush=True)
    print(
        f"Symbols: {', '.join(symbols)} | Equity: {capital:.2f} | "
        f"Max concurrent: {max_concurrent} | {mtf}",
        flush=True,
    )


def print_portfolio_header(symbols: list, capital: float, *, max_concurrent: int = 1) -> None:
    print("\n=== PORTFOLIO MODE ===", flush=True)
    print(
        f"Symbols: {', '.join(symbols)} | Capital: {capital:.2f} | "
        f"Max concurrent: {max_concurrent}",
        flush=True,
    )


def structure_scan(
    symbol: str,
    structure_tf: str,
    state_text: str,
    candle_time: datetime,
    *,
    note: str = "",
) -> None:
    """Deprecated: structure diagnostics use ``market_structure.event_log`` (file only)."""
    import logging

    extra = f" | {note}" if note else ""
    logging.getLogger(__name__).info(
        "[STRUCTURE] %s TF=%s %s%s | %s",
        symbol,
        structure_tf,
        state_text,
        extra,
        _ts(candle_time),
    )


def portfolio_pick(prospect: object, candle_time: datetime, *, verbose: bool = True) -> None:
    line = (
        f"[PICK] {prospect.symbol} {prospect.side.upper()} "
        f"score={prospect.score:.0f} | {_ts(candle_time)}"
    )
    print(line, flush=True)
    if verbose and getattr(prospect, "reasons", None):
        from strategy.signal_quality import format_breakdown

        detail = format_breakdown(prospect.reasons)
        if detail:
            print(f"       score_detail: {detail}", flush=True)


def execution_levels(
    side: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    candle_time: datetime,
    *,
    tp_r: float | None = None,
) -> None:
    """Print SL/TP levels at entry."""
    risk = (entry - stop_loss) if side == "long" else (stop_loss - entry)
    reward = (take_profit - entry) if side == "long" else (entry - take_profit)
    rr = (reward / risk) if risk > 0 else 0.0
    sl_pct = (risk / entry * 100) if entry > 0 else 0.0
    tp_label = f"{tp_r:.0f}R runner" if tp_r is not None and tp_r > 1 else f"R:R={rr:.1f}"
    print(
        f"[LEVELS] SL={stop_loss:.4f} ({sl_pct:.2f}% = 1R) "
        f"TP={take_profit:.4f} ({tp_label}) | {_ts(candle_time)}",
        flush=True,
    )


def trail_sl(
    symbol: str,
    side: str,
    event: object,
    candle_time: datetime,
) -> None:
    lock_r = getattr(event, "lock_r", 0.0)
    lock_label = "breakeven (0R)" if lock_r == 0 else f"+{lock_r:.0f}R"
    milestone = getattr(event, "milestone_r", 0.0)
    new_sl = getattr(event, "new_sl", 0.0)
    label = "LONG" if side == "long" else "SHORT"
    sym = f"{symbol} " if symbol else ""
    print(
        f"[TRAIL-SL] {sym}{label} +{milestone:.0f}R → SL at {lock_label} ({new_sl:.4f}) | "
        f"{_ts(candle_time)}",
        flush=True,
    )


def scan_near_miss(symbol: str, score: float) -> None:
    print(
        f"[SCAN] No trades taken. Best near-miss: {symbol} score={score:.0f} "
        f"(check MIN_SIGNAL_SCORE / structure filters)",
        flush=True,
    )


def print_symbol_header(symbol: str, params: dict | None = None) -> None:
    print(f"\n========== {symbol} ==========", flush=True)
    if params:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
        print(f"Params: {parts}", flush=True)


def multi_symbol_summary(
    symbols: list,
    initial_per_symbol: float,
    combined_pnl: float,
    combined_trades: int,
) -> None:
    print("\n--- Combined Multi-Symbol Summary ---", flush=True)
    print(f"Symbols:         {', '.join(symbols)}", flush=True)
    print(f"Capital/symbol:  {initial_per_symbol:.2f}", flush=True)
    print(f"Combined PnL:    {combined_pnl:+.2f}", flush=True)
    print(f"Total trades:    {combined_trades}", flush=True)
    print("-------------------------------------\n", flush=True)


def backtest_report(
    initial: float,
    final: float,
    pnl: float,
    funding: float,
    metrics: object,
    exit_summary: object | None = None,
) -> None:
    print("\n--- Backtest Report ---", flush=True)
    print(f"Initial Capital: {initial:.2f}", flush=True)
    print(f"Final Capital:   {final:.2f}", flush=True)
    print(f"Total PnL:       {pnl:.2f}", flush=True)
    print(f"Total Funding:   {funding:.2f}", flush=True)
    print(f"Metrics:         {metrics}", flush=True)
    if exit_summary is not None:
        print("Exit Summary:", flush=True)
        print(
            f"  Take Profit:  {exit_summary.take_profit:3d}  "
            f"(PnL {exit_summary.take_profit_pnl:+.2f})",
            flush=True,
        )
        print(
            f"  Stop Loss:    {exit_summary.stop_loss:3d}  "
            f"(PnL {exit_summary.stop_loss_pnl:+.2f})",
            flush=True,
        )
        print(
            f"  Trend Exit:   {exit_summary.trend_exit:3d}  "
            f"(PnL {exit_summary.trend_exit_pnl:+.2f})",
            flush=True,
        )
        print(
            f"  Partial Profit: {exit_summary.partial_profit:3d}  "
            f"(PnL {exit_summary.partial_profit_pnl:+.2f})",
            flush=True,
        )
        if exit_summary.max_drawdown:
            print(
                f"  Max Drawdown: {exit_summary.max_drawdown:3d}  "
                f"(PnL {exit_summary.max_drawdown_pnl:+.2f})",
                flush=True,
            )
        if exit_summary.other:
            print(
                f"  Other:        {exit_summary.other:3d}  "
                f"(PnL {exit_summary.other_pnl:+.2f})",
                flush=True,
            )
        print(
            f"  Total exits:  {exit_summary.total:3d}",
            flush=True,
        )
    print("-----------------------\n", flush=True)

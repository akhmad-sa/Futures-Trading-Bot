"""
Trade history report for Telegram /trade_status (reads SQLite).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass(frozen=True)
class SymbolSummary:
    symbol: str
    trades: int
    wins: int
    losses: int
    total_pnl: float

    @property
    def win_rate_pct(self) -> float:
        if self.trades == 0:
            return 0.0
        return self.wins / self.trades * 100.0


@dataclass(frozen=True)
class TradeReport:
    recent: list[dict[str, Any]]
    by_symbol: list[SymbolSummary]
    total_trades: int
    total_wins: int
    total_losses: int
    total_pnl: float

    @property
    def win_rate_pct(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_wins / self.total_trades * 100.0


def _fmt_time(raw: str) -> str:
    if not raw or not str(raw).strip():
        return "—"
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return str(raw)[:19]


def _fmt_pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}"


def _summarize_rows(rows: list[dict[str, Any]]) -> TradeReport:
    by_sym: dict[str, SymbolSummary] = {}
    total_wins = total_losses = 0
    total_pnl = 0.0

    for row in rows:
        symbol = str(row.get("symbol") or "?")
        pnl = float(row.get("pnl") or 0.0)
        total_pnl += pnl
        if pnl >= 0:
            total_wins += 1
        else:
            total_losses += 1

        prev = by_sym.get(symbol)
        if prev is None:
            by_sym[symbol] = SymbolSummary(
                symbol=symbol,
                trades=1,
                wins=1 if pnl >= 0 else 0,
                losses=0 if pnl >= 0 else 1,
                total_pnl=pnl,
            )
        else:
            by_sym[symbol] = SymbolSummary(
                symbol=symbol,
                trades=prev.trades + 1,
                wins=prev.wins + (1 if pnl >= 0 else 0),
                losses=prev.losses + (0 if pnl >= 0 else 1),
                total_pnl=prev.total_pnl + pnl,
            )

    ranked = sorted(by_sym.values(), key=lambda s: s.total_pnl, reverse=True)
    return TradeReport(
        recent=rows,
        by_symbol=ranked,
        total_trades=len(rows),
        total_wins=total_wins,
        total_losses=total_losses,
        total_pnl=total_pnl,
    )


async def load_trade_report(
    db_path: str | Path,
    *,
    recent_limit: int = 10,
) -> TradeReport:
    """Load recent trades + summaries from trade history DB."""
    path = Path(db_path)
    if not path.is_file():
        return TradeReport([], [], 0, 0, 0, 0.0)

    limit = max(1, min(int(recent_limit), 50))
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT id, symbol, side, entry_price, exit_price, quantity, "
            "entry_time, exit_time, pnl FROM trades ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            recent = [dict(row) for row in await cursor.fetchall()]

        async with conn.execute(
            "SELECT symbol, pnl FROM trades ORDER BY id ASC"
        ) as cursor:
            all_rows = [dict(row) for row in await cursor.fetchall()]

    summary = _summarize_rows(all_rows)
    return TradeReport(
        recent=recent,
        by_symbol=summary.by_symbol,
        total_trades=summary.total_trades,
        total_wins=summary.total_wins,
        total_losses=summary.total_losses,
        total_pnl=summary.total_pnl,
    )


def format_trade_report(report: TradeReport, *, recent_limit: int = 10) -> str:
    """Format trade report for Telegram (compact)."""
    if report.total_trades == 0:
        return "📊 Trade Status\n\nBelum ada trade tercatat di database."

    lines = ["📊 Trade Status", ""]

    lines.append(f"Recent ({min(len(report.recent), recent_limit)}):")
    for row in report.recent[:recent_limit]:
        when = _fmt_time(str(row.get("exit_time") or row.get("entry_time") or ""))
        symbol = row.get("symbol", "?")
        side = str(row.get("side", "")).upper()[:1] or "?"
        pnl = float(row.get("pnl") or 0.0)
        emoji = "🟢" if pnl >= 0 else "🔴"
        lines.append(f"{emoji} {when} | {symbol} {side} | {_fmt_pnl(pnl)}")

    if report.by_symbol:
        lines.append("")
        lines.append("By pair:")
        for sym in report.by_symbol:
            lines.append(
                f"• {sym.symbol}: {sym.trades} trade(s) | "
                f"W{sym.wins}/L{sym.losses} | {_fmt_pnl(sym.total_pnl)}"
            )

    lines.append("")
    lines.append("Summary:")
    lines.append(
        f"Total: {report.total_trades} trade(s) | "
        f"Win {report.total_wins} / Loss {report.total_losses} "
        f"({report.win_rate_pct:.0f}%)"
    )
    lines.append(f"Total PnL: {_fmt_pnl(report.total_pnl)}")

    return "\n".join(lines)

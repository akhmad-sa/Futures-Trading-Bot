"""
Backtest metrics computation.
"""

import math
from typing import List

from backtest.models import TradeRecord


class MetricsResult:
    """Container for all computed performance metrics."""

    def __init__(
        self,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        winrate: float,
        gross_profit: float,
        gross_loss: float,
        profit_factor: float,
        sharpe_ratio: float,
        max_drawdown: float,
        max_drawdown_pct: float,
    ) -> None:
        self.total_trades = total_trades
        self.winning_trades = winning_trades
        self.losing_trades = losing_trades
        self.winrate = winrate
        self.gross_profit = gross_profit
        self.gross_loss = gross_loss
        self.profit_factor = profit_factor
        self.sharpe_ratio = sharpe_ratio
        self.max_drawdown = max_drawdown
        self.max_drawdown_pct = max_drawdown_pct

    @staticmethod
    def empty() -> "MetricsResult":
        return MetricsResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            winrate=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            profit_factor=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
        )

    def __repr__(self) -> str:
        return (
            f"MetricsResult(total_trades={self.total_trades}, "
            f"winning_trades={self.winning_trades}, "
            f"losing_trades={self.losing_trades}, "
            f"winrate={self.winrate:.4f}, "
            f"profit_factor={self.profit_factor:.4f}, "
            f"sharpe_ratio={self.sharpe_ratio:.4f}, "
            f"max_drawdown_pct={self.max_drawdown_pct:.4%})"
        )


def compute_metrics(
    initial_capital: float,
    final_capital: float,
    equity_curve: list[float],
    trades: list[TradeRecord],
) -> MetricsResult:
    """Compute all performance metrics from a backtest run."""
    total_trades = len(trades)
    if total_trades == 0:
        return MetricsResult.empty()

    winning_trades = sum(1 for t in trades if t.pnl > 0)
    losing_trades = total_trades - winning_trades
    winrate = winning_trades / total_trades if total_trades else 0.0

    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = sum(abs(t.pnl) for t in trades if t.pnl < 0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown (absolute and percentage)
    peak = equity_curve[0]
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_drawdown:
            max_drawdown = dd
        if peak > 0:
            dd_pct = (peak - equity) / peak
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

    # Sharpe ratio (annualized, assuming risk‑free rate = 0)
    # Each step corresponds to one candle. Use per‑step returns.
    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            r = (equity_curve[i] - prev) / prev
            returns.append(r)

    if len(returns) < 2:
        sharpe_ratio = 0.0
    else:
        avg_r = sum(returns) / len(returns)
        variance = sum((r - avg_r) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance) if variance > 0 else 1e-10
        # Approximate number of periods per year (5‑minute bars)
        periods_per_year = 252 * 24 * 12  # 5 minutes each
        sharpe_ratio = (avg_r / std) * math.sqrt(periods_per_year)

    return MetricsResult(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        winrate=winrate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
    )

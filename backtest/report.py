"""
Performance report produced by a backtest run.
"""

from dataclasses import dataclass, field
from typing import List

from backtest.models import TradeRecord
from backtest.metrics import MetricsResult


@dataclass
class PerformanceReport:
    """Complete report of a backtest run."""

    initial_capital: float
    final_capital: float
    total_pnl: float
    total_funding_fees: float
    metrics: MetricsResult
    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "PerformanceReport":
        return cls(
            initial_capital=0.0,
            final_capital=0.0,
            total_pnl=0.0,
            total_funding_fees=0.0,
            metrics=MetricsResult.empty(),
            trades=[],
            equity_curve=[],
        )

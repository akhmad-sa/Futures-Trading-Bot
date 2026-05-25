"""
Simple backtesting engine that replays OHLCV data.
"""

from typing import Any
import pandas as pd
import numpy as np


class BacktestEngine:
    """Lightweight backtester with basic performance metrics."""

    def __init__(self, initial_capital: float = 10000.0) -> None:
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.equity_curve: list[float] = [initial_capital]
        self.trades: list[dict[str, Any]] = []

    def run(self, ohlcv: pd.DataFrame, strategy) -> dict[str, float]:
        """
        Run the backtest over a DataFrame with columns: timestamp, open, high, low, close, volume.

        The strategy must have a ``get_signal(symbol, ohlcv_list)`` method that
        returns 'long', 'short', or 'close'.
        """
        # Placeholder – real implementation would iterate rows and execute signals.
        # For now, just compute dummy metrics.
        self._compute_metrics()
        return self.metrics

    def _compute_metrics(self) -> None:
        """Calculate winrate, max drawdown, Sharpe ratio, etc."""
        if not self.equity_curve:
            self.metrics = {"winrate": 0.0, "max_drawdown": 0.0, "sharpe": 0.0}
            return

        equity = pd.Series(self.equity_curve)
        returns = equity.pct_change().dropna()

        winrate = float((returns > 0).mean())

        # max drawdown
        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min())

        # sharpe ratio (assuming risk‑free rate = 0)
        if returns.std() > 0:
            sharpe = float(returns.mean() / returns.std() * np.sqrt(252 * 24 * 60 // 5))  # for 5‑min bars
        else:
            sharpe = 0.0

        self.metrics = {
            "winrate": round(winrate, 4),
            "max_drawdown": round(max_drawdown, 4),
            "sharpe": round(sharpe, 4),
        }

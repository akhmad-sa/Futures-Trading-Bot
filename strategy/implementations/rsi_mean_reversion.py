"""
RSI mean reversion strategy.

Generates signals based on RSI crossing oversold/overbought thresholds.
"""

import logging
from typing import List, Any

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class RsiMeanReversionStrategy(BaseStrategy):
    name = "rsi_mean_reversion"
    description = "RSI mean reversion strategy (period=14, oversold=30, overbought=70)."

    def __init__(self, config: Any = None, symbols: List[str] = None,
                 enabled: bool = True, rsi_period: int = 14,
                 oversold: float = 30.0, overbought: float = 70.0, **kwargs):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Return ``'long'`` when RSI crosses below oversold threshold,
        ``'close'`` when RSI crosses above overbought threshold,
        ``'hold'`` otherwise.
        """
        if len(candles) < self.rsi_period + 2:
            return "hold"

        closes = [c.close for c in candles]

        current_rsi = self._rsi(closes, self.rsi_period, len(closes))
        prev_rsi = self._rsi(closes, self.rsi_period, len(closes) - 1)

        if prev_rsi > self.oversold and current_rsi <= self.oversold:
            logger.info("RSI crossed below oversold -> LONG")
            return "long"
        elif prev_rsi < self.overbought and current_rsi >= self.overbought:
            logger.info("RSI crossed above overbought -> CLOSE")
            return "close"
        return "hold"

    @staticmethod
    def _rsi(values: List[float], period: int, lookback: int) -> float:
        """Compute RSI for the last `period` values."""
        if lookback < period + 1:
            raise ValueError(f"lookback {lookback} < period+1 {period+1}")
        deltas = [values[i] - values[i - 1] for i in range(lookback - period, lookback)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        avg_gain = sum(gains) / period if gains else 0.0
        avg_loss = sum(losses) / period if losses else 0.0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

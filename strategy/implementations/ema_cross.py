"""
EMA crossover strategy.

Generates signals based on the crossing of a fast and slow EMA.
Uses close prices from the candle history.
"""

import logging
from typing import List, Any

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class EmaCrossStrategy(BaseStrategy):
    name = "ema_cross"
    description = "EMA crossover strategy (fast=12, slow=26)."

    def __init__(self, config: Any = None, symbols: List[str] = None,
                 enabled: bool = True, fast_period: int = 12,
                 slow_period: int = 26, **kwargs):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Return ``'long'`` when fast EMA crosses above slow EMA,
        ``'close'`` when fast EMA crosses below slow EMA,
        ``'hold'`` otherwise.

        Uses simple moving average as a fast approximation of EMA.
        """
        if len(candles) < self.slow_period + 1:
            return "hold"

        closes = [c.close for c in candles]

        fast_ema = self._ema(closes, self.fast_period, len(closes))
        slow_ema = self._ema(closes, self.slow_period, len(closes))

        prev_fast = self._ema(closes, self.fast_period, len(closes) - 1)
        prev_slow = self._ema(closes, self.slow_period, len(closes) - 1)

        if prev_fast <= prev_slow and fast_ema > slow_ema:
            logger.info("EMA cross: fast EMA crossed above slow EMA -> LONG")
            return "long"
        elif prev_fast >= prev_slow and fast_ema < slow_ema:
            logger.info("EMA cross: fast EMA crossed below slow EMA -> CLOSE")
            return "close"
        return "hold"

    @staticmethod
    def _ema(values: List[float], period: int, lookback: int) -> float:
        """Simple exponential moving average (approximation)."""
        if lookback < period:
            raise ValueError(f"lookback {lookback} < period {period}")
        multiplier = 2.0 / (period + 1)
        # Start with SMA
        start = lookback - period
        sma = sum(values[start:start + period]) / period
        ema = sma
        for i in range(start + period, lookback):
            ema = (values[i] - ema) * multiplier + ema
        return ema

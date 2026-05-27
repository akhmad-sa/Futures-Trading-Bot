"""
EMA crossover strategy.

Generates signals based on the crossing of a fast and slow EMA.
Uses close prices from the candle history.

Includes optional filters to reduce whipsaw:
- confirmation_candles: number of consecutive candles the crossover must persist
- min_distance_bps: minimum distance between fast and slow EMA (in basis points)
- cooldown_candles: minimum number of candles between trades
"""

import logging
from typing import Any, List, Optional

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class EmaCrossStrategy(BaseStrategy):
    name = "ema_cross"
    description = "EMA crossover strategy (fast=12, slow=26) with optional whipsaw filters."

    def __init__(
        self,
        config: Any = None,
        symbols: List[str] = None,
        enabled: bool = True,
        fast_period: int = 12,
        slow_period: int = 26,
        confirmation_candles: int = 0,
        min_distance_bps: float = 0.0,
        cooldown_candles: int = 0,
        **kwargs,
    ):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.confirmation_candles = confirmation_candles
        self.min_distance_bps = min_distance_bps
        self.cooldown_candles = cooldown_candles

        # Internal state for debounce
        self._last_trade_candle: int = -self.cooldown_candles - 1
        self._crossover_direction: Optional[str] = None
        self._crossover_count: int = 0

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Return ``'long'`` when fast EMA crosses above slow EMA,
        ``'close'`` when fast EMA crosses below slow EMA,
        ``'hold'`` otherwise.

        Whipsaw filters:
        - confirmation_candles: crossover must persist for N consecutive candles
        - min_distance_bps: fast/slow distance must exceed threshold
        - cooldown_candles: minimum candles between trades
        """
        if len(candles) < self.slow_period + 1:
            return "hold"

        closes = [c.close for c in candles]

        fast_ema = self._ema(closes, self.fast_period, len(closes))
        slow_ema = self._ema(closes, self.slow_period, len(closes))

        prev_fast = self._ema(closes, self.fast_period, len(closes) - 1)
        prev_slow = self._ema(closes, self.slow_period, len(closes) - 1)

        # Determine current crossover direction
        current_direction: Optional[str] = None
        if prev_fast <= prev_slow and fast_ema > slow_ema:
            current_direction = "long"
        elif prev_fast >= prev_slow and fast_ema < slow_ema:
            current_direction = "close"

        # Update confirmation counter
        if current_direction == self._crossover_direction:
            self._crossover_count += 1
        else:
            self._crossover_direction = current_direction
            self._crossover_count = 1 if current_direction is not None else 0

        # Check cooldown
        candle_index = len(candles) - 1
        if candle_index - self._last_trade_candle < self.cooldown_candles:
            return "hold"

        # Check minimum distance
        if self.min_distance_bps > 0:
            distance_bps = abs(fast_ema - slow_ema) / slow_ema * 10_000
            if distance_bps < self.min_distance_bps:
                return "hold"

        # Check confirmation
        if self._crossover_count < self.confirmation_candles:
            return "hold"

        # Generate signal
        if current_direction == "long":
            logger.info(
                "EMA cross: fast EMA crossed above slow EMA (conf=%d, dist=%.1f bps) -> LONG",
                self._crossover_count,
                abs(fast_ema - slow_ema) / slow_ema * 10_000,
            )
            self._last_trade_candle = candle_index
            return "long"
        elif current_direction == "close":
            logger.info(
                "EMA cross: fast EMA crossed below slow EMA (conf=%d, dist=%.1f bps) -> CLOSE",
                self._crossover_count,
                abs(fast_ema - slow_ema) / slow_ema * 10_000,
            )
            self._last_trade_candle = candle_index
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

"""
Example strategy: EMA crossover + RSI filter + volume confirmation.
"""

from typing import Any
from .base import BaseStrategy
from indicators.ema import ema
from indicators.rsi import rsi
from indicators.volume_sma import volume_sma


class ExampleStrategy(BaseStrategy):
    """Simple EMA crossover strategy with RSI and volume confirmation."""

    def __init__(self, config) -> None:
        self.config = config
        self.fast_period = 12
        self.slow_period = 26
        self.rsi_period = 14
        self.rsi_overbought = 70
        self.rsi_oversold = 30
        self.volume_sma_period = 20

    async def get_signal(self, symbol: str, ohlcv: list[list]) -> str:
        """
        Evaluate the latest signal based on recent OHLCV data.

        ohlcv is a list of candles: [timestamp, open, high, low, close, volume]
        """
        if len(ohlcv) < self.slow_period + self.rsi_period:
            return "hold"

        closes = [c[4] for c in ohlcv]
        volumes = [c[5] for c in ohlcv]

        ema_fast = ema(closes, self.fast_period)
        ema_slow = ema(closes, self.slow_period)
        rsi_vals = rsi(closes, self.rsi_period)
        vol_sma_vals = volume_sma(volumes, self.volume_sma_period)

        # Ensure all arrays have the same length
        n = min(len(ema_fast), len(ema_slow), len(rsi_vals), len(vol_sma_vals))
        if n == 0:
            return "hold"

        last_ema_fast = ema_fast[-1]
        last_ema_slow = ema_slow[-1]
        prev_ema_fast = ema_fast[-2] if len(ema_fast) >= 2 else last_ema_fast
        prev_ema_slow = ema_slow[-2] if len(ema_slow) >= 2 else last_ema_slow
        last_rsi = rsi_vals[-1]
        last_volume = volumes[-1]
        last_vol_sma = vol_sma_vals[-1]

        volume_ok = last_volume > last_vol_sma

        # Long signal: fast crosses above slow, RSI > oversold, volume confirmation
        if prev_ema_fast <= prev_ema_slow and last_ema_fast > last_ema_slow:
            if last_rsi > self.rsi_oversold and volume_ok:
                return "long"

        # Short signal: fast crosses below slow, RSI < overbought, volume confirmation
        if prev_ema_fast >= prev_ema_slow and last_ema_fast < last_ema_slow:
            if last_rsi < self.rsi_overbought and volume_ok:
                return "short"

        # Close signal could be added based on opposite cross etc.
        return "hold"

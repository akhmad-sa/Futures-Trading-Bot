"""
Example strategy: EMA crossover + RSI filter + volume confirmation.
Uses the centralised market data service.
"""

from typing import Any, Optional, List

from .base import BaseStrategy
from indicators.ema import ema
from indicators.rsi import rsi
from indicators.volume_sma import volume_sma


class ExampleStrategy(BaseStrategy):
    """Simple EMA crossover strategy with RSI and volume confirmation."""

    name = "ExampleStrategy"

    def __init__(
        self,
        config,
        symbols: Optional[List[str]] = None,
        enabled: bool = True,
        fast_period: int = 12,
        slow_period: int = 26,
        rsi_period: int = 14,
        rsi_overbought: int = 70,
        rsi_oversold: int = 30,
        volume_sma_period: int = 20,
    ) -> None:
        super().__init__(config, symbols, enabled)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.volume_sma_period = volume_sma_period

    async def generate_signal(self, symbol: str) -> str:
        """Evaluate the latest signal using the centralised market data service."""
        # Retrieve candles from the service
        if self.market_data_service is None:
            raise RuntimeError(
                "MarketDataService is not set. Call set_market_data_service() first."
            )
        timeframe = getattr(self.config, "timeframe", "1m")
        candles = await self.market_data_service.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=self.slow_period + self.rsi_period + 50,  # ensure enough data
        )

        if len(candles) < self.slow_period + self.rsi_period:
            return "hold"

        # Convert to the lists expected by the indicator functions
        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]

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

        return "hold"

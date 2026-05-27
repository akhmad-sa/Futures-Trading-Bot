"""
Golden test strategy – deterministic validation strategy.

Buys (long) on the first candle and closes after a configurable number
of candles (default 5).  Logs candle count and generated signals for
pipeline validation.
"""

import logging
from typing import List, Any

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class GoldenTestStrategy(BaseStrategy):
    name = "golden_test"
    description = (
        "Deterministic test strategy: enters long on the first candle, "
        "closes after N candles (default 5)."
    )

    def __init__(self, config: Any = None, symbols: List[str] = None,
                 enabled: bool = True, close_after: int = 5, **kwargs):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)
        self.close_after = close_after

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Return signals:
        - ``'long'`` on the first candle (len==1)
        - ``'close'`` after *close_after* candles
        - ``'hold'`` otherwise.

        Logs candle count and the returned signal.
        """
        candle_count = len(candles)
        signal: str = "hold"

        if candle_count == 1:
            signal = "long"
        elif candle_count == self.close_after:
            signal = "close"

        logger.info(
            "GoldenTestStrategy | symbol=%s | candle_count=%d | signal=%s",
            symbol, candle_count, signal,
        )
        return signal

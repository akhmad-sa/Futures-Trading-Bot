"""
Golden test strategy – deterministic validation strategy.

Buys (long) on the first candle and closes after a configurable number
of candles (default 5).  Used to validate replay, execution, and
portfolio accounting correctness.
"""

from strategy.base import BaseStrategy
from typing import List, Any


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
        """
        if len(candles) == 1:
            return "long"
        if len(candles) == self.close_after:
            return "close"
        return "hold"

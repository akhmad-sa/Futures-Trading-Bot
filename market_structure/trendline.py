"""
Trendline construction and detection.

Builds a trendline connecting the last two confirmed swing highs
(resistance) or swing lows (support).  Trendlines are only recomputed
when a new confirmed pivot appears, preventing repainting.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from market_data.models.candle import Candle
from market_structure.pivots import detect_swing_highs, detect_swing_lows


@dataclass
class Trendline:
    """
    Represents a straight line defined by two points (x1, y1) -> (x2, y2).

    The x‑coordinates correspond to candle indices; y‑coordinates are
    prices.  The line can be extrapolated to any index.
    """
    is_support: bool  # True for support (connecting lows), False for resistance (highs)
    x1: int
    y1: float
    x2: int
    y2: float

    def price_at(self, x: int) -> float:
        """Interpolate the trendline price at candle index *x*."""
        if self.x2 == self.x1:
            return self.y1
        slope = (self.y2 - self.y1) / (self.x2 - self.x1)
        return self.y1 + slope * (x - self.x1)


def build_trendlines(
    candles: List[Candle],
    left: int = 2,
    right: int = 2,
) -> List[Trendline]:
    """
    Build trendlines from the two most recent confirmed swing highs
    (resistance) and two most recent confirmed swing lows (support).

    Only pivots that are fully confirmed (have the required right‑side
    candles) are used, ensuring the trendline does not repaint.

    Returns a list of at most two :class:`Trendline` objects (one support,
    one resistance).  If not enough swings exist, the list may be empty.
    """
    highs = detect_swing_highs(candles, left, right)
    lows = detect_swing_lows(candles, left, right)

    trendlines: List[Trendline] = []

    # Resistance from last two confirmed highs
    if len(highs) >= 2:
        h1 = highs[-2]
        h2 = highs[-1]
        trendlines.append(
            Trendline(is_support=False, x1=h1, y1=candles[h1].high,
                      x2=h2, y2=candles[h2].high)
        )
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(
            "Built resistance trendline from high idx %d (%.2f) to %d (%.2f)",
            h1, candles[h1].high, h2, candles[h2].high,
        )

    # Support from last two confirmed lows
    if len(lows) >= 2:
        l1 = lows[-2]
        l2 = lows[-1]
        trendlines.append(
            Trendline(is_support=True, x1=l1, y1=candles[l1].low,
                      x2=l2, y2=candles[l2].low)
        )
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(
            "Built support trendline from low idx %d (%.2f) to %d (%.2f)",
            l1, candles[l1].low, l2, candles[l2].low,
        )

    return trendlines

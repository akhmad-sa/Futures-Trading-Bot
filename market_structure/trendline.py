"""
Trendline construction and detection.

Builds a trendline connecting the last two confirmed swing highs
(resistance) or swing lows (support).  Trendlines are only recomputed
when a new confirmed pivot appears, preventing repainting.

Supports filters to ignore weak pivots:
- min_pivot_spacing: minimum number of candles between pivots
- min_price_delta_pct: minimum price change between pivots (as fraction)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from market_data.models.candle import Candle
from market_structure.pivots import detect_swing_highs, detect_swing_lows

import logging

logger = logging.getLogger(__name__)


@dataclass
class Trendline:
    """
    Represents a straight line defined by two points (x1, y1) -> (x2, y2).

    The x‑coordinates correspond to candle indices; y‑coordinates are
    prices.  The line can be extrapolated to any index.

    Lifecycle attributes track when the trendline was built, when it was
    last touched, and whether it has been consumed by a breakout.
    """
    is_support: bool  # True for support (connecting lows), False for resistance (highs)
    x1: int
    y1: float
    x2: int
    y2: float

    # Lifecycle
    created_at_index: int = -1   # index of the second pivot (when it became confirmed)
    last_touch_index: int = -1   # index of the most recent candle that touched the line
    breakout_index: int = -1     # index of the breakout candle (if any)
    consumed: bool = False       # True after a confirmed breakout has been processed
    active: bool = True          # False after trendline expires or is consumed
    strength_score: float = 0.0  # future: number of touches, slope stability (not yet used)

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
    min_pivot_spacing: int = 3,
    min_price_delta_pct: float = 0.005,
) -> List[Trendline]:
    """
    Build trendlines from the two most recent confirmed swing highs
    (resistance) and two most recent confirmed swing lows (support).

    Only pivots that are fully confirmed (have the required right‑side
    candles) are used, ensuring the trendline does not repaint.

    Parameters
    ----------
    candles : List[Candle]
        Historical candle data.
    left, right : int
        Lookback parameters for pivot detection.
    min_pivot_spacing : int
        Minimum number of candles between the two pivots used to build a
        trendline.  Pivot pairs closer than this are ignored (weak lines).
    min_price_delta_pct : float
        Minimum price difference (as fraction of the first pivot price)
        between the two pivots.  Smaller differences indicate a flat line
        and are ignored.

    Returns
    -------
    List[Trendline]
        At most two trendlines (one support, one resistance).  Empty list
        if not enough strong pivots exist.
    """
    highs = detect_swing_highs(candles, left, right)
    lows = detect_swing_lows(candles, left, right)

    trendlines: List[Trendline] = []

    # Resistance from last two confirmed highs (most recent)
    if len(highs) >= 2:
        h1 = highs[-2]
        h2 = highs[-1]
        # Filter: minimum spacing
        if abs(h2 - h1) >= min_pivot_spacing:
            price1 = candles[h1].high
            price2 = candles[h2].high
            # Filter: minimum price delta (fraction)
            delta = abs(price2 - price1) / price1
            if delta >= min_price_delta_pct:
                trendlines.append(
                    Trendline(
                        is_support=False,
                        x1=h1, y1=price1,
                        x2=h2, y2=price2,
                        created_at_index=h2,
                        last_touch_index=h2,
                        active=True,
                    )
                )
                logger.info(
                    "Trendline created: resistance from high idx %d (%.2f, time=%d) to %d (%.2f, time=%d)",
                    h1, price1, candles[h1].timestamp,
                    h2, price2, candles[h2].timestamp,
                )
            else:
                logger.debug(
                    "Resistance trendline skipped: price delta %.4f < min %.4f",
                    delta, min_price_delta_pct,
                )
        else:
            logger.debug(
                "Resistance trendline skipped: pivot spacing %d < min %d",
                abs(h2 - h1), min_pivot_spacing,
            )

    # Support from last two confirmed lows (most recent)
    if len(lows) >= 2:
        l1 = lows[-2]
        l2 = lows[-1]
        if abs(l2 - l1) >= min_pivot_spacing:
            price1 = candles[l1].low
            price2 = candles[l2].low
            delta = abs(price2 - price1) / price1
            if delta >= min_price_delta_pct:
                trendlines.append(
                    Trendline(
                        is_support=True,
                        x1=l1, y1=price1,
                        x2=l2, y2=price2,
                        created_at_index=l2,
                        last_touch_index=l2,
                        active=True,
                    )
                )
                logger.info(
                    "Trendline created: support from low idx %d (%.2f, time=%d) to %d (%.2f, time=%d)",
                    l1, price1, candles[l1].timestamp,
                    l2, price2, candles[l2].timestamp,
                )
            else:
                logger.debug(
                    "Support trendline skipped: price delta %.4f < min %.4f",
                    delta, min_price_delta_pct,
                )
        else:
            logger.debug(
                "Support trendline skipped: pivot spacing %d < min %d",
                abs(l2 - l1), min_pivot_spacing,
            )

    return trendlines

"""
Pivot detection (swing highs / swing lows) with configurable lookback.

Avoids repainting by using a fixed number of candles before and after
the candidate pivot.  Swings are only confirmed once the required
*right* candles have closed, making the detection safe for real‑time
replay.
"""

import logging
from typing import List, Optional, Tuple

from market_data.models.candle import Candle

logger = logging.getLogger(__name__)


def detect_swing_highs(
    candles: List[Candle], left: int = 2, right: int = 2
) -> List[int]:
    """
    Return indices of candles that are higher than *left* candles before
    and *right* candles after (i.e. a local maximum).

    The lookback parameters *left* and *right* determine the pivot strength.
    Larger values produce fewer, stronger pivots.

    .. note::
        This function uses **only confirmed** candles.  The last *right*
        candles of the input list are **not** considered as potential pivots
        because there are not enough future candles to confirm them.
    """
    highs: List[int] = []
    n = len(candles)
    if n < left + right + 1:
        return highs
    # Only iterate over indices that have *right* future candles
    for i in range(left, n - right):
        price = candles[i].high
        valid = True

        # Check left side
        for j in range(i - left, i):
            if candles[j].high >= price:
                valid = False
                break
        if not valid:
            continue

        # Check right side (these candles are already closed in backtest)
        for j in range(i + 1, i + right + 1):
            if candles[j].high >= price:
                valid = False
                break
        if valid:
            highs.append(i)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Swing high at index %d, price=%.2f, time=%d",
                    i, price, candles[i].timestamp,
                )

    return highs


def detect_swing_lows(
    candles: List[Candle], left: int = 2, right: int = 2
) -> List[int]:
    """
    Return indices of candles that are lower than *left* candles before
    and *right* candles after (i.e. a local minimum).

    Same repaint‑safety rules as :func:`detect_swing_highs`.
    """
    lows: List[int] = []
    n = len(candles)
    if n < left + right + 1:
        return lows
    for i in range(left, n - right):
        price = candles[i].low
        valid = True

        for j in range(i - left, i):
            if candles[j].low <= price:
                valid = False
                break
        if not valid:
            continue

        for j in range(i + 1, i + right + 1):
            if candles[j].low <= price:
                valid = False
                break
        if valid:
            lows.append(i)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Swing low at index %d, price=%.2f, time=%d",
                    i, price, candles[i].timestamp,
                )

    return lows


def detect_pivots(
    candles: List[Candle], left: int = 2, right: int = 2
) -> List[Tuple[int, str]]:
    """
    Return a list of (index, type) where type is ``'high'`` or ``'low'``.

    The list is sorted by index and contains only confirmed pivots.
    """
    highs = detect_swing_highs(candles, left, right)
    lows = detect_swing_lows(candles, left, right)
    combined: List[Tuple[int, str]] = [(i, "high") for i in highs] + [
        (i, "low") for i in lows
    ]
    combined.sort(key=lambda x: x[0])
    for idx, typ in combined:
        if logger.isEnabledFor(logging.INFO):
            logger.info(
                "Pivot confirmed: index=%d, type=%s, price=%.2f, time=%d",
                idx, typ,
                candles[idx].high if typ == "high" else candles[idx].low,
                candles[idx].timestamp,
            )
    return combined

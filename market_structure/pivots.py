"""
Pivot detection (swing highs / swing lows) with configurable lookback.

Avoids repainting by using a fixed number of candles before and after
the candidate pivot.
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
    """
    highs: List[int] = []
    n = len(candles)
    if n < left + right + 1:
        return highs
    for i in range(left, n - right):
        price = candles[i].high
        valid = True
        for j in range(i - left, i):
            if candles[j].high >= price:
                valid = False
                break
        if not valid:
            continue
        for j in range(i + 1, i + right + 1):
            if candles[j].high >= price:
                valid = False
                break
        if valid:
            highs.append(i)
    return highs


def detect_swing_lows(
    candles: List[Candle], left: int = 2, right: int = 2
) -> List[int]:
    """
    Return indices of candles that are lower than *left* candles before
    and *right* candles after (i.e. a local minimum).
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
    return lows


def detect_pivots(
    candles: List[Candle], left: int = 2, right: int = 2
) -> List[Tuple[int, str]]:
    """
    Return a list of (index, type) where type is ``'high'`` or ``'low'``.
    """
    highs = detect_swing_highs(candles, left, right)
    lows = detect_swing_lows(candles, left, right)
    combined: List[Tuple[int, str]] = [(i, "high") for i in highs] + [
        (i, "low") for i in lows
    ]
    combined.sort(key=lambda x: x[0])
    return combined

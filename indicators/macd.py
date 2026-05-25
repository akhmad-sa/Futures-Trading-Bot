"""
MACD indicator (moving average convergence divergence).
"""

from typing import List, Tuple
from .ema import ema


def macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Compute MACD line, signal line, and histogram.

    Returns tuple (macd_line, signal_line, histogram).
    """
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)

    min_len = min(len(ema_fast), len(ema_slow))
    ema_fast = ema_fast[-min_len:]
    ema_slow = ema_slow[-min_len:]

    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)

    # Trim to same length
    min_len2 = min(len(macd_line), len(signal_line))
    macd_line = macd_line[-min_len2:]
    signal_line = signal_line[-min_len2:]
    histogram = [m - s for m, s in zip(macd_line, signal_line)]

    return macd_line, signal_line, histogram

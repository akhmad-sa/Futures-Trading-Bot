"""
Exponential Moving Average.
"""

from typing import List


def ema(prices: List[float], period: int) -> List[float]:
    """
    Compute EMA for the given price series.

    Returns a list of EMA values, length = len(prices) - period + 1.
    """
    if len(prices) < period:
        return []

    multiplier = 2.0 / (period + 1)
    result = [sum(prices[:period]) / period]

    for price in prices[period:]:
        val = (price - result[-1]) * multiplier + result[-1]
        result.append(val)

    return result

"""
Simple Moving Average of volume.
"""

from typing import List


def volume_sma(volumes: List[float], period: int = 20) -> List[float]:
    """
    Compute SMA of volume series.

    Returns a list of SMA values, length = len(volumes) - period + 1.
    """
    if len(volumes) < period:
        return []

    result: List[float] = []
    for i in range(period - 1, len(volumes)):
        sma = sum(volumes[i - period + 1 : i + 1]) / period
        result.append(sma)

    return result

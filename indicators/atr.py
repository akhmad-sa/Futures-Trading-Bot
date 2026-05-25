"""
Average True Range.
"""

from typing import List


def atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> List[float]:
    """
    Compute ATR for the given price series.

    Returns a list of ATR values, length = len(highs) - period.
    """
    if len(highs) < period + 1:
        return []

    tr_list: List[float] = []
    for i in range(1, len(highs)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))

    atr_values: List[float] = [sum(tr_list[:period]) / period]
    for i in range(period, len(tr_list)):
        atr_values.append(
            (atr_values[-1] * (period - 1) + tr_list[i]) / period
        )

    return atr_values

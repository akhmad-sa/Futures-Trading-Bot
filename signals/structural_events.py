"""
Explicit event objects for market structure signals.

These events are consumed by strategies instead of directly inspecting
internal pivot / trendline / breakout state.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BreakoutEvent:
    """
    Emitted when a confirmed breakout is detected.

    Attributes
    ----------
    direction : str
        ``"above"`` (resistance breakout) or ``"below"`` (support breakdown).
    candle_index : int
        Index of the candle that confirmed the breakout.
    line_price : float
        Price of the trendline at the breakout candle.
    close_price : float
        Close price of the breakout candle.
    timestamp_ms : int
        Timestamp of the breakout candle (milliseconds).
    confidence : int
        Number of consecutive candles that confirmed the breakout.
    """

    direction: str
    candle_index: int
    line_price: float
    close_price: float
    timestamp_ms: int
    confidence: int = 1


@dataclass
class TrendlineEvent:
    """
    Emitted when a new trendline is built or updated.

    Attributes
    ----------
    is_support : bool
        ``True`` for support (connecting lows), ``False`` for resistance (highs).
    x1 : int
        Candle index of the first pivot.
    y1 : float
        Price of the first pivot.
    x2 : int
        Candle index of the second pivot.
    y2 : float
        Price of the second pivot.
    timestamp_ms : int
        Timestamp of the most recent pivot (milliseconds).
    """

    is_support: bool
    x1: int
    y1: float
    x2: int
    y2: float
    timestamp_ms: int


@dataclass
class PivotEvent:
    """
    Emitted when a new pivot is confirmed.

    Attributes
    ----------
    pivot_type : str
        ``"high"`` or ``"low"``.
    candle_index : int
        Index of the pivot candle.
    price : float
        Price of the pivot (high for high, low for low).
    timestamp_ms : int
        Timestamp of the pivot candle (milliseconds).
    """

    pivot_type: str
    candle_index: int
    price: float
    timestamp_ms: int

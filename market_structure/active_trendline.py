"""
Persistent trendline with per-line lifecycle and breakout detector.
"""

from dataclasses import dataclass
from typing import Optional

from market_structure.trendline import Trendline
from market_structure.breakout import BreakoutDetector


@dataclass
class ActiveTrendline:
    """
    A trendline that persists across candles with its own lifecycle and
    breakout detector.

    Attributes
    ----------
    id : str
        Unique identifier (e.g. ``"R12"`` for resistance #12, ``"S7"`` for support #7).
    line : Trendline
        The underlying geometric line.
    created_index : int
        Candle index when the trendline was created.
    last_touch_index : int
        Candle index of the most recent close that touched the line.
    breakout_count : int
        Number of confirmed breakouts on this line (currently at most 1).
    is_valid : bool
        ``True`` while the line is still structurally valid (not expired, not broken).
    is_broken : bool
        ``True`` after a confirmed breakout.
    expired : bool
        ``True`` after the line surpasses its maximum age.
    breakout_detector : BreakoutDetector, optional
        Per‑line breakout detector.  Never shared between lines.
    """

    id: str
    line: Trendline
    created_index: int
    last_touch_index: int = -1
    breakout_count: int = 0
    is_valid: bool = True
    is_broken: bool = False
    expired: bool = False
    breakout_detector: Optional[BreakoutDetector] = None

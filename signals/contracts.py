"""
Single source of truth for all event dataclasses.
Only this file defines event schemas.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BreakoutEvent:
    """Emitted when a confirmed breakout is detected."""
    direction: str  # "above" or "below"
    candle_index: int
    line_price: float
    close_price: float
    timestamp_ms: int
    trendline_id: Optional[str] = None

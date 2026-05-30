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


@dataclass
class PivotClassifiedEvent:
    """Emitted when a swing pivot receives an HH/HL/LH/LL label."""
    pivot_type: str  # "high" or "low"
    label: str  # HH, HL, LH, LL, EH, EL, or empty for first pivot
    candle_index: int
    price: float
    timestamp_ms: int
    trend_structure: str  # uptrend, downtrend, neutral


@dataclass
class StructureBreakEvent:
    """Emitted on BOS or CHoCH (see market_structure.bos_choch)."""
    kind: str  # bos_bullish, bos_bearish, choch_bullish, choch_bearish
    candle_index: int
    close_price: float
    broken_level: float
    broken_swing_index: int
    broken_swing_type: str  # "high" or "low"
    timestamp_ms: int
    bias_after: str  # uptrend, downtrend, neutral

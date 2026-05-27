"""
Explicit event objects for market structure signals.

These events are emitted by the :class:`MarketStructureEngine` and
consumed by strategies.
"""

from dataclasses import dataclass
from typing import Optional


class StructuralEvent:
    """Base class for all structural events."""
    pass


@dataclass
class PivotEvent(StructuralEvent):
    """Emitted when a new pivot is confirmed."""
    pivot_type: str       # "high" or "low"
    candle_index: int
    price: float
    timestamp_ms: int


@dataclass
class TrendlineCreatedEvent(StructuralEvent):
    """Emitted when a new active trendline is created."""
    trendline_id: str
    is_support: bool
    x1: int
    y1: float
    x2: int
    y2: float
    slope: float
    timestamp_ms: int


@dataclass
class TrendlineInvalidatedEvent(StructuralEvent):
    """Emitted when a trendline becomes invalid (expired or broken)."""
    trendline_id: str
    reason: str            # "expired", "broken"
    candle_index: int
    timestamp_ms: int


@dataclass
class BreakoutEvent(StructuralEvent):
    """Emitted when a confirmed breakout is detected on a trendline."""
    trendline_id: str
    direction: str         # "above" (resistance) or "below" (support)
    candle_index: int
    line_price: float
    close_price: float
    distance_bps: float
    timestamp_ms: int
    confidence: int = 1

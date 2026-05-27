"""
Dataclasses representing swing high / low points.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SwingHigh:
    """A swing high (local maximum) detected by the pivot detector."""
    candle_index: int
    price: float
    timestamp_ms: int


@dataclass
class SwingLow:
    """A swing low (local minimum) detected by the pivot detector."""
    candle_index: int
    price: float
    timestamp_ms: int

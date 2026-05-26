"""
Unified candle model used across the entire project.

Immutable dataclass with strongly typed fields.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    timestamp: int  # milliseconds since epoch (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""
    timeframe: str = ""
    exchange: str = ""

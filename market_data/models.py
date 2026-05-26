from dataclasses import dataclass
from typing import List


@dataclass
class Candle:
    timestamp: int  # UNIX timestamp in seconds or milliseconds, consistent
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_list(self) -> list:
        """Convert to list format used by legacy strategies."""
        return [self.timestamp, self.open, self.high, self.low, self.close, self.volume]

    @classmethod
    def from_list(cls, lst: list) -> 'Candle':
        """Create Candle from list [timestamp, open, high, low, close, volume]."""
        return cls(
            timestamp=int(lst[0]),
            open=float(lst[1]),
            high=float(lst[2]),
            low=float(lst[3]),
            close=float(lst[4]),
            volume=float(lst[5]),
        )

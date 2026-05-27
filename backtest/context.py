from dataclasses import dataclass
from typing import Optional


@dataclass
class BacktestContext:
    """Holds the date range for a backtest run."""
    start_time: Optional[int] = None  # milliseconds since epoch (UTC)
    end_time: Optional[int] = None

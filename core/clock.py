"""
Unified simulation clock for backtest and live modes.

Provides a deterministic time source that can be set and advanced.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional


class SimulationClock:
    """Simulation clock that can be set to a specific timestamp or run in real time."""

    def __init__(self, fixed_time: Optional[datetime] = None) -> None:
        self._current_time: datetime = (
            fixed_time if fixed_time is not None else datetime.now(timezone.utc)
        )

    def now(self) -> datetime:
        """Return the current simulation time."""
        return self._current_time

    def set_time(self, dt: datetime) -> None:
        """Set the clock to a specific datetime (must be UTC)."""
        self._current_time = dt

    def advance(self, seconds: float) -> None:
        """Advance the clock by the given number of seconds."""
        self._current_time += timedelta(seconds=seconds)

    def set_from_timestamp_ms(self, timestamp_ms: int) -> None:
        """Set time from a millisecond timestamp (UTC)."""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        self._current_time = dt

    @classmethod
    def from_backtest_start(cls, start_time_ms: int) -> "SimulationClock":
        """Create a clock initialised to a backtest start time."""
        dt = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)
        return cls(fixed_time=dt)

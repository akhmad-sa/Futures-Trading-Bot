"""
Tracks open positions.
"""

from typing import Any, Optional


class PositionManager:
    """Manages active positions."""

    def __init__(self) -> None:
        self._active_positions: dict[str, dict] = {}

    def add_position(self, symbol: str, entry: dict) -> None:
        self._active_positions[symbol] = entry

    def remove_position(self, symbol: str) -> Optional[dict]:
        return self._active_positions.pop(symbol, None)

    @property
    def positions_count(self) -> int:
        return len(self._active_positions)

    def get_position(self, symbol: str) -> Optional[dict]:
        return self._active_positions.get(symbol)

    def clear(self) -> None:
        self._active_positions.clear()

"""
Abstract base class for trading strategies.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    """Interface that all strategies must implement."""

    @abstractmethod
    async def get_signal(self, symbol: str, ohlcv: list[list]) -> str:
        """
        Return the trading signal for a given symbol.

        Returns one of 'long', 'short', 'close', or 'hold'.
        """

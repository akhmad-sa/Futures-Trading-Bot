"""
Abstract base class for trading strategies.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class BaseStrategy(ABC):
    """Interface that all strategies must implement."""

    name: str = "base"  # override in subclass

    def __init__(
        self,
        config,
        symbols: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> None:
        self.config = config
        self.symbols = symbols or []
        self.enabled = enabled

    @abstractmethod
    async def get_signal(self, symbol: str, ohlcv: list[list]) -> str:
        """
        Return the trading signal for a given symbol.

        Returns one of 'long', 'short', 'close', or 'hold'.
        """

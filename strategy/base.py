"""
Abstract base class for trading strategies.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from market_data.models import Candle
from market_data.services import MarketDataService


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
        self.market_data_service: Optional[MarketDataService] = None

    def set_market_data_service(self, service: MarketDataService) -> None:
        """Attach the centralised market data service instance."""
        self.market_data_service = service

    @abstractmethod
    async def generate_signal(self, symbol: str) -> str:
        """
        Return the trading signal for a given symbol, using the attached
        market_data_service to obtain candle data.

        Returns one of 'long', 'short', 'close', or 'hold'.
        """
        ...

    async def get_signal(self, symbol: str, ohlcv: List[List]) -> str:
        """
        Legacy method – receives raw OHLCV list.
        Override this or the new generate_signal method.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement generate_signal"
        )

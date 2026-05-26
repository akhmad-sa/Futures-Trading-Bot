"""
Abstract data provider interface for market data.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List

from core.models.candle import Candle


class DataProvider(ABC):
    """Interface for fetching historical and realtime candle data."""

    @abstractmethod
    async def fetch_historical(
        self,
        symbol: str,
        timeframe: str,
        since: int,
        limit: int = 100,
    ) -> List[Candle]:
        """
        Fetch historical candles.

        Args:
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            timeframe: Candle timeframe (e.g. '1h', '5m')
            since: Starting timestamp in milliseconds
            limit: Maximum number of candles to return

        Returns:
            List of Candle objects sorted by timestamp ascending.
        """
        raise NotImplementedError

    @abstractmethod
    async def subscribe_realtime(
        self,
        symbol: str,
        timeframe: str,
    ) -> AsyncIterator[Candle]:
        """
        Subscribe to realtime candle updates.

        Returns an async iterator that yields new Candle objects as they arrive.
        """
        raise NotImplementedError

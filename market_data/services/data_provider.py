from abc import ABC, abstractmethod
from typing import List, Optional

from market_data.models.candle import Candle


class DataProvider(ABC):
    """Abstract base class for all market data providers."""

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 10_000,
        since: Optional[int] = None,
    ) -> List[Candle]:
        ...

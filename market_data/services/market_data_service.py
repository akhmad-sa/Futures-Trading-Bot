from typing import List, Optional, Union

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider
from market_data.services.historical_data_provider import HistoricalDataProvider


class MarketDataService:
    """
    Centralised market data service that abstracts the data source.

    Can be initialised with a :class:`DataProvider` (live or historical)
    or with a plain list of :class:`Candle` objects (for backtesting).
    """

    def __init__(
        self,
        provider: Union[DataProvider, List[Candle], None] = None,
    ) -> None:
        if isinstance(provider, list):
            self._provider: DataProvider = HistoricalDataProvider(provider)
        else:
            self._provider = provider

    def set_provider(self, provider: DataProvider) -> None:
        """Replace the current data provider at runtime."""
        self._provider = provider

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 10_000,
        since: Optional[int] = None,
    ) -> List[Candle]:
        if self._provider is None:
            raise RuntimeError("No data provider configured")
        return await self._provider.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=since,
        )

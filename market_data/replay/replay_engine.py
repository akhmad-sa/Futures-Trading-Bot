from typing import AsyncGenerator, List, Optional

from market_data import MarketDataService
from market_data.models.candle import Candle


class ReplayEngine:
    """
    Deterministic replay engine that iterates over historical candles
    in sequential, chunked batches.
    """

    def __init__(self, service: MarketDataService) -> None:
        self._service = service

    async def replay(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        chunk_size: int = 10_000,
    ) -> AsyncGenerator[List[Candle], None]:
        """
        Yield lists of :class:`Candle` objects in ascending order,
        each containing up to ``chunk_size`` candles.
        """
        all_candles = await self._service.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )
        for i in range(0, len(all_candles), chunk_size):
            yield all_candles[i : i + chunk_size]

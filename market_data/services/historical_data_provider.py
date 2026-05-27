from typing import List, Optional

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider


class HistoricalDataProvider(DataProvider):
    """Provider that returns a pre‑loaded list of candles (e.g. for backtesting)."""

    def __init__(self, candles: List[Candle]) -> None:
        self._candles = candles

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 10_000,
        since: Optional[int] = None,
    ) -> List[Candle]:
        return self._candles

from typing import List, Optional

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider


class LiveDataProvider(DataProvider):
    """Provider that fetches live candles from an exchange (ccxt)."""

    def __init__(self, exchange_id: str = "default") -> None:
        self._exchange_id = exchange_id
        # TODO: initialise ccxt exchange instance

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 10_000,
        since: Optional[int] = None,
    ) -> List[Candle]:
        raise NotImplementedError("Live data provider not implemented yet")

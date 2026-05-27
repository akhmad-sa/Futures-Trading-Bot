from typing import List, Optional

import ccxt.async_support as ccxt

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider


EXCHANGE_NAME_MAP = {
    "binance": ccxt.binance,
    "bybit": ccxt.bybit,
    "mexc": ccxt.mexc,
}


class LiveDataProvider(DataProvider):
    """Provider that fetches live candles from an exchange (ccxt)."""

    def __init__(self, exchange_id: str = "default") -> None:
        self._exchange_id = exchange_id

    async def get_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        limit: int = 10_000,
        since: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Candle]:
        ex_id = exchange.lower()
        if ex_id not in EXCHANGE_NAME_MAP:
            print(f"Unsupported exchange: {exchange}")
            return []
        exchange_cls = EXCHANGE_NAME_MAP[ex_id]
        ex = exchange_cls()
        try:
            # Use start_time as 'since' if provided, otherwise fall back to 'since' argument
            use_since = start_time if start_time is not None else since
            ohlcv = await ex.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=use_since,
                limit=limit,
            )
            raw = [
                Candle(
                    timestamp=item[0],
                    open=item[1],
                    high=item[2],
                    low=item[3],
                    close=item[4],
                    volume=item[5],
                )
                for item in ohlcv
            ]
            # Apply end_time filter if provided
            if end_time is not None:
                raw = [c for c in raw if c.timestamp <= end_time]
            return raw
        except Exception as e:
            print(f"Live data fetch failed: {e}")
            return []
        finally:
            await ex.close()

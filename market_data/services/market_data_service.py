import os
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider
from market_data.services.historical_data_provider import HistoricalDataProvider
from market_data.services.live_data_provider import LiveDataProvider


class MarketDataService:
    """
    Centralised market data service that abstracts the data source.

    Can be initialised with a :class:`DataProvider` (live or historical)
    or with a plain list of :class:`Candle` objects (for backtesting).
    """

    def __init__(
        self,
        provider: Union[DataProvider, List[Candle], None] = None,
        data_dir: str = "data/candles",
    ) -> None:
        if isinstance(provider, list):
            self._provider: DataProvider = HistoricalDataProvider(provider)
        else:
            self._provider = provider
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def set_provider(self, provider: DataProvider) -> None:
        """Replace the current data provider at runtime."""
        self._provider = provider

    # ------------------------------------------------------------------
    # Storage paths
    # ------------------------------------------------------------------
    def _filepath(self, exchange: str, symbol: str, timeframe: str) -> Path:
        return (
            self._data_dir
            / exchange.lower()
            / symbol.replace("/", "_")
            / f"{timeframe}.parquet"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
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
        """
        Retrieve candles for the given exchange/symbol/timeframe.

        If local data exists (Parquet) it is used; otherwise the
        configured provider is queried and the result is stored.
        """
        # Try local storage first
        local = self._load_candles_from_storage(
            exchange, symbol, timeframe, start_time, end_time
        )
        if local is not None and len(local) > 0:
            return local

        # Fall back to provider
        if self._provider is None:
            raise RuntimeError("No data provider configured")

        fetched = await self._provider.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=since,
            start_time=start_time,
            end_time=end_time,
        )
        if fetched:
            self._store_candles_to_storage(exchange, symbol, timeframe, fetched)
        return fetched

    async def store_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
    ) -> None:
        """Persist the provided candles to local Parquet storage."""
        self._store_candles_to_storage(exchange, symbol, timeframe, candles)

    async def replay_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Candle]:
        """
        Replay historical candles from local storage.
        Currently returns the full list; can be extended to yield chunks.
        """
        return await self.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )

    # ------------------------------------------------------------------
    # Internal storage helpers
    # ------------------------------------------------------------------
    def _load_candles_from_storage(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Optional[List[Candle]]:
        fpath = self._filepath(exchange, symbol, timeframe)
        if not fpath.exists():
            return None
        try:
            df = pd.read_parquet(fpath)
        except Exception:
            return None
        if df.empty:
            return []

        # Filter by time range
        if start_time is not None:
            df = df[df["timestamp"] >= start_time]
        if end_time is not None:
            df = df[df["timestamp"] <= end_time]

        # Convert back to Candle objects
        candles = []
        for _, row in df.iterrows():
            candles.append(
                Candle(
                    timestamp=row["timestamp"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
            )
        return candles

    def _store_candles_to_storage(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
    ) -> None:
        if not candles:
            return
        fpath = self._filepath(exchange, symbol, timeframe)
        fpath.parent.mkdir(parents=True, exist_ok=True)

        # Build DataFrame from new candles
        new_df = pd.DataFrame(
            [
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ]
        )

        # Merge with existing file if present, deduplicate on timestamp
        if fpath.exists():
            existing_df = pd.read_parquet(fpath)
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
            combined = combined.sort_values("timestamp").reset_index(drop=True)
            combined.to_parquet(fpath, index=False)
        else:
            new_df.to_parquet(fpath, index=False)

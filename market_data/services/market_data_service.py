import os
from pathlib import Path
from typing import List, Optional, Tuple, Union

import pandas as pd

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider
from market_data.services.historical_data_provider import HistoricalDataProvider
from market_data.services.live_data_provider import LiveDataProvider
from market_data.ingestion.historical_downloader import HistoricalDownloader


class MarketDataService:
    """
    Centralised market data service that abstracts the data source.

    Can be initialised with a :class:`DataProvider` (live or historical)
    or with a plain list of :class:`Candle` objects (for backtesting).

    When a :class:`LiveDataProvider` is used, the service automatically
    downloads missing historical data via the :class:`HistoricalDownloader`
    and stores it locally in Parquet format.
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

        # Prepare a downloader for live providers
        self._downloader: Optional[HistoricalDownloader] = None
        if isinstance(self._provider, LiveDataProvider):
            # The exchange id is stored inside the provider; we can retrieve it
            # via a public attribute (we'll add one if needed). For now we
            # assume the provider has an _exchange_id attribute.
            ex_id = getattr(self._provider, "_exchange_id", "default")
            self._downloader = HistoricalDownloader(exchange_id=ex_id)

    def set_provider(self, provider: DataProvider) -> None:
        """Replace the current data provider at runtime."""
        self._provider = provider
        # Re‑create downloader if needed
        if isinstance(self._provider, LiveDataProvider):
            ex_id = getattr(self._provider, "_exchange_id", "default")
            self._downloader = HistoricalDownloader(exchange_id=ex_id)
        else:
            self._downloader = None

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
        When a :class:`LiveDataProvider` is active, missing data is
        automatically downloaded and cached.

        Returns
        -------
        List[Candle]
            Always returns a list (possibly empty). Never returns None.
        """
        # Try local storage first
        local = self._load_candles_from_storage(
            exchange, symbol, timeframe, start_time, end_time
        )
        if local is not None and len(local) > 0:
            print(f"dataset found: {len(local)} candles")
            # Check if we need to fetch additional data (incremental)
            missing_ranges = self._compute_missing_ranges(
                local, start_time, end_time
            )
            if not missing_ranges:
                print(f"candles loaded: {len(local)}")
                return local

            # Fetch missing ranges and store them
            for miss_start, miss_end in missing_ranges:
                print("fetching missing candles...")
                fetched = await self._download_range(
                    exchange, symbol, timeframe, miss_start, miss_end
                )
                if fetched:
                    print(f"candles fetched: {len(fetched)}")
                    self._store_candles_to_storage(
                        exchange, symbol, timeframe, fetched
                    )

            # Reload the full range after storing
            result = self._load_candles_from_storage(
                exchange, symbol, timeframe, start_time, end_time
            )
            if result is None:
                result = []
            print(f"candles loaded: {len(result)}")
            return result

        # No local data – fetch the full requested range
        print("dataset missing")
        print("fetching candles...")
        fetched = await self._download_range(
            exchange, symbol, timeframe, start_time, end_time
        )
        if fetched:
            print(f"candles fetched: {len(fetched)}")
            self._store_candles_to_storage(exchange, symbol, timeframe, fetched)
        result = self._load_candles_from_storage(
            exchange, symbol, timeframe, start_time, end_time
        )
        if result is None:
            result = []
        print(f"candles loaded: {len(result)}")
        return result

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

        Returns
        -------
        List[Candle]
            Always returns a list (possibly empty). Never returns None.
        """
        return await self.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compute_missing_ranges(
        self,
        local_candles: List[Candle],
        start_time: Optional[int],
        end_time: Optional[int],
    ) -> List[Tuple[int, int]]:
        """
        Given a list of locally stored candles (sorted by timestamp),
        return a list of (start, end) millisecond ranges that are
        missing from the requested [start_time, end_time] interval.
        """
        if not local_candles:
            return []

        local_min = local_candles[0].timestamp
        local_max = local_candles[-1].timestamp

        ranges: List[Tuple[int, int]] = []

        # Missing before local data
        if start_time is not None and start_time < local_min:
            ranges.append((start_time, local_min - 1))

        # Missing after local data
        if end_time is not None and end_time > local_max:
            ranges.append((local_max + 1, end_time))

        return ranges

    async def _download_range(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int],
        end_time: Optional[int],
    ) -> List[Candle]:
        """
        Download candles for the given range using the configured
        downloader (if available) or fall back to the provider.

        Returns
        -------
        List[Candle]
            Always returns a list (possibly empty). Never returns None.
        """
        if self._downloader is not None:
            try:
                return await self._downloader.download_range(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_time=start_time,
                    end_time=end_time,
                )
            except Exception as e:
                print(f"Download failed: {e}")
                return []

        # Fall back to the generic provider (e.g. HistoricalDataProvider)
        if self._provider is None:
            print("No data provider configured")
            return []

        try:
            return await self._provider.get_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                limit=10_000,
                since=start_time,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            print(f"Provider fetch failed: {e}")
            return []

    def _load_candles_from_storage(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Optional[List[Candle]]:
        """
        Load candles from local Parquet storage.

        Returns
        -------
        Optional[List[Candle]]
            None if the file does not exist or cannot be read.
            Otherwise a list (possibly empty) of Candle objects.
        """
        fpath = self._filepath(exchange, symbol, timeframe)
        if not fpath.exists():
            return None
        try:
            df = pd.read_parquet(fpath)
        except Exception as e:
            print(f"Failed to read parquet file {fpath}: {e}")
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
            try:
                existing_df = pd.read_parquet(fpath)
            except Exception as e:
                print(f"Failed to read existing parquet file {fpath}: {e}")
                existing_df = pd.DataFrame()
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
            combined = combined.sort_values("timestamp").reset_index(drop=True)
            combined.to_parquet(fpath, index=False)
        else:
            new_df.to_parquet(fpath, index=False)

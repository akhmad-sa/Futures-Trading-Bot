import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

import pandas as pd

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider
from market_data.services.historical_data_provider import HistoricalDataProvider
from market_data.services.live_data_provider import LiveDataProvider
from market_data.ingestion.historical_downloader import HistoricalDownloader
from market_data.dataset_sync import (
    DatasetInfo,
    build_dataset_info,
    compute_missing_ranges as sync_compute_missing_ranges,
    log_dataset_audit,
    log_sync_plan,
)

logger = logging.getLogger(__name__)


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
            ex_id = getattr(self._provider, "_exchange_id", "default")
            self._downloader = HistoricalDownloader(exchange_id=ex_id)

    def set_provider(self, provider: DataProvider) -> None:
        """Replace the current data provider at runtime."""
        self._provider = provider
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
        *,
        max_stale_days: float = 1.0,
    ) -> List[Candle]:
        """
        Retrieve candles for the given exchange/symbol/timeframe.

        Uses local Parquet when available; downloads and appends missing
        ranges (including tail staleness > *max_stale_days*).
        """
        full_local = self._load_candles_from_storage(
            exchange, symbol, timeframe, None, None
        )
        if full_local is None:
            full_local = []

        can_sync = self._downloader is not None
        stale_days = max_stale_days if can_sync else 1e9
        gap_days = 1.0 if can_sync else 1e9

        missing_ranges = sync_compute_missing_ranges(
            full_local,
            start_time=start_time,
            end_time=end_time,
            max_stale_days=stale_days,
            max_internal_gap_days=gap_days,
        )

        if full_local:
            logger.info("dataset found: %d candles", len(full_local))
        else:
            logger.info("dataset missing")

        if missing_ranges:
            for miss_start, miss_end in missing_ranges:
                logger.info("fetching missing candles...")
                fetched = await self._download_range(
                    exchange, symbol, timeframe, miss_start, miss_end
                )
                if fetched:
                    logger.info("candles fetched: %d", len(fetched))
                    self._store_candles_to_storage(
                        exchange, symbol, timeframe, fetched
                    )
        elif full_local:
            logger.info("candles loaded: %d", len(full_local))

        result = self._load_candles_from_storage(
            exchange, symbol, timeframe, start_time, end_time
        )
        if result is None:
            result = []
        if not result and not full_local:
            logger.warning("empty dataset retrieved")
        logger.info("candles loaded: %d", len(result))
        return result

    async def ensure_dataset_fresh(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        *,
        max_stale_days: float = 1.0,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> DatasetInfo:
        """
        Audit local dataset time range; sync and append if stale or gapped.

        Call before backtest so Parquet stays current for development.
        """
        fpath = self._filepath(exchange, symbol, timeframe)
        full_local = self._load_candles_from_storage(
            exchange, symbol, timeframe, None, None
        )
        if full_local is None:
            full_local = []

        info = build_dataset_info(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            path=str(fpath),
            candles=full_local if full_local else None,
        )
        log_dataset_audit(info)

        ranges = sync_compute_missing_ranges(
            full_local,
            start_time=start_time,
            end_time=end_time,
            max_stale_days=max_stale_days,
        )
        log_sync_plan(info, ranges, max_stale_days=max_stale_days)

        if not ranges and not full_local:
            logger.info(
                "[DATASET] %s %s — initial download (no local file)",
                symbol,
                timeframe,
            )
            await self.get_candles(
                exchange,
                symbol,
                timeframe,
                start_time=start_time,
                end_time=end_time,
                max_stale_days=max_stale_days,
            )
            updated = self._load_candles_from_storage(
                exchange, symbol, timeframe, None, None
            ) or []
            info = build_dataset_info(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                path=str(fpath),
                candles=updated if updated else None,
            )
            log_dataset_audit(info)
        elif ranges:
            total_fetched = 0
            for miss_start, miss_end in ranges:
                fetched = await self._download_range(
                    exchange, symbol, timeframe, miss_start, miss_end
                )
                if fetched:
                    total_fetched += len(fetched)
                    self._store_candles_to_storage(
                        exchange, symbol, timeframe, fetched
                    )
            updated = self._load_candles_from_storage(
                exchange, symbol, timeframe, None, None
            ) or []
            logger.info(
                "[DATASET] %s %s — appended %d candles (total %d)",
                symbol,
                timeframe,
                total_fetched,
                len(updated),
            )
            info = build_dataset_info(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                path=str(fpath),
                candles=updated if updated else None,
            )
            log_dataset_audit(info)

        return info

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
                logger.error("Download failed: %s", e)
                return []

        # Fall back to the generic provider (e.g. HistoricalDataProvider)
        if self._provider is None:
            logger.warning("No data provider configured")
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
            logger.error("Provider fetch failed: %s", e)
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
            logger.error("Failed to read parquet file %s: %s", fpath, e)
            return None
        if df.empty:
            return []

        df = df.sort_values("timestamp").reset_index(drop=True)

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

        if fpath.exists():
            try:
                existing_df = pd.read_parquet(fpath)
            except Exception as e:
                logger.error("Failed to read existing parquet file %s: %s", fpath, e)
                existing_df = pd.DataFrame()
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
            combined = combined.sort_values("timestamp").reset_index(drop=True)
            combined.to_parquet(fpath, index=False)
        else:
            new_df.to_parquet(fpath, index=False)

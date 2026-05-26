"""
Centralized Market Data Service.

Provides shared candle cache, realtime updates, historical loading,
and an event‑driven subscription system.
Consumers (strategies, backtesting, etc.) do not know the data source.
"""

import asyncio
from typing import AsyncIterator, Dict, List, Optional, Tuple

from core.models.candle import Candle
from core.market_data.provider import DataProvider


class MarketDataService:
    """Async service managing market data for all consumers."""

    def __init__(self) -> None:
        # Exchange -> provider mapping
        self._providers: Dict[str, DataProvider] = {}
        # Key: (exchange, symbol, timeframe) -> list of candles (sorted ascending)
        self._cache: Dict[Tuple[str, str, str], List[Candle]] = {}
        # Subscribers: key -> list of asyncio.Queue[Candle]
        self._subscribers: Dict[Tuple[str, str, str], List[asyncio.Queue]] = {}
        # Background tasks for realtime feeds
        self._tasks: Dict[Tuple[str, str, str], asyncio.Task] = {}
        # Lock for thread safety (though asyncio single‑threaded, still guard)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Provider registration
    # ------------------------------------------------------------------
    def register_provider(self, exchange: str, provider: DataProvider) -> None:
        """Register a data provider for a given exchange."""
        self._providers[exchange] = provider

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------
    async def get_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        since: Optional[int] = None,
    ) -> List[Candle]:
        """
        Return cached candles, fetching from provider if necessary.

        If `since` is provided, only candles with timestamp >= since are returned.
        If not in cache, fetches from provider and stores in cache.
        """
        key = (exchange, symbol, timeframe)
        async with self._lock:
            cached = self._cache.get(key, [])

        # If we have enough cached data and no since, return limit from end
        if cached and since is None:
            return cached[-limit:]

        # Need to fetch from provider
        if since is None:
            # Use last cached timestamp as since to get new data
            last_ts = cached[-1].timestamp if cached else 0
            since = last_ts

        provider = self._get_provider(exchange)
        candles = await provider.fetch_historical(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=limit,
        )
        # Merge with cache
        async with self._lock:
            existing = self._cache.get(key, [])
            # Simple append, assumes data is newer
            existing.extend(candles)
            # Sort unique by timestamp (could be duplicates)
            seen = set()
            merged: List[Candle] = []
            for c in sorted(existing, key=lambda x: x.timestamp):
                if c.timestamp not in seen:
                    seen.add(c.timestamp)
                    merged.append(c)
            self._cache[key] = merged
            return merged[-limit:] if limit else merged

    # ------------------------------------------------------------------
    # Subscription / realtime
    # ------------------------------------------------------------------
    async def subscribe(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> asyncio.Queue:
        """
        Subscribe to realtime candle updates.

        Returns an :class:`asyncio.Queue` from which consumers can await new
        :class:`Candle` objects.
        """
        key = (exchange, symbol, timeframe)
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            subscribers = self._subscribers.setdefault(key, [])
            subscribers.append(queue)
            # Start realtime feed if not already running
            if key not in self._tasks:
                self._tasks[key] = asyncio.create_task(
                    self._run_realtime_feed(exchange, symbol, timeframe)
                )
        return queue

    async def unsubscribe(
        self, exchange: str, symbol: str, timeframe: str, queue: asyncio.Queue
    ) -> None:
        """Remove a subscriber queue."""
        key = (exchange, symbol, timeframe)
        async with self._lock:
            subscribers = self._subscribers.get(key, [])
            if queue in subscribers:
                subscribers.remove(queue)
            # If no subscribers left, stop the realtime feed task
            if not subscribers and key in self._tasks:
                self._tasks[key].cancel()
                del self._tasks[key]

    async def subscribe_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> AsyncIterator[Candle]:
        """
        Async generator that yields new candle updates.

        Use::

            async for candle in service.subscribe_candles("binance", "BTC/USDT", "1m"):
                print(candle)

        Automatically unsubscribes when the generator terminates.
        """
        queue = await self.subscribe(exchange, symbol, timeframe)
        try:
            while True:
                candle = await queue.get()
                yield candle
        except asyncio.CancelledError:
            raise
        finally:
            await self.unsubscribe(exchange, symbol, timeframe, queue)

    async def _run_realtime_feed(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Background task that reads from provider's realtime iterator and pushes to all subscribers."""
        provider = self._get_provider(exchange)
        try:
            async for candle in provider.subscribe_realtime(symbol, timeframe):
                # Update cache
                await self._add_candle_to_cache(exchange, symbol, timeframe, candle)
                # Push to all subscribers
                async with self._lock:
                    subscribers = self._subscribers.get(
                        (exchange, symbol, timeframe), []
                    ).copy()
                for q in subscribers:
                    # Non‑blocking put; drop oldest if queue full (simplification)
                    try:
                        q.put_nowait(candle)
                    except asyncio.QueueFull:
                        pass  # drop oldest
        except asyncio.CancelledError:
            # Task cancelled; cleanup is done by caller
            pass
        except Exception:
            # Log error and restart? For now ignore
            pass

    async def _add_candle_to_cache(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        candle: Candle,
    ) -> None:
        key = (exchange, symbol, timeframe)
        async with self._lock:
            cached = self._cache.setdefault(key, [])
            # Avoid duplicates and support in‑place updates
            if not cached or cached[-1].timestamp < candle.timestamp:
                cached.append(candle)
            elif cached[-1].timestamp == candle.timestamp:
                # Replace the most recent candle (e.g. realtime update)
                cached[-1] = candle
            else:
                # Out‑of‑order insertion (rare)
                cached.append(candle)
                cached.sort(key=lambda x: x.timestamp)

    # ------------------------------------------------------------------
    # Bulk candle injection (used by historical data ingestion)
    # ------------------------------------------------------------------
    async def add_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
    ) -> None:
        """
        Inject a batch of candles into the shared cache (e.g. from a
        historical data file).  The candles are merged with any existing
        cache data, deduplicated, and sorted by timestamp.

        This method does **not** push candles to realtime subscribers;
        it is intended only for populating historical data.
        """
        key = (exchange, symbol, timeframe)
        async with self._lock:
            existing = self._cache.get(key, [])
            # Merge
            all_candles = existing + candles
            # Deduplicate by timestamp, sorted
            seen: set[int] = set()
            merged: List[Candle] = []
            for c in sorted(all_candles, key=lambda x: x.timestamp):
                if c.timestamp not in seen:
                    seen.add(c.timestamp)
                    merged.append(c)
            self._cache[key] = merged

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_provider(self, exchange: str) -> DataProvider:
        provider = self._providers.get(exchange)
        if provider is None:
            raise ValueError(
                f"No data provider registered for exchange '{exchange}'"
            )
        return provider

"""
Historical data downloader with pagination, retry, and rate‑limit handling.

Fetches OHLCV candles from supported exchanges (Binance, Bybit, MEXC)
using the ccxt async library.  Designed to be used by the
:class:`MarketDataService` when local storage is missing or incomplete.
"""

import asyncio
from typing import List, Optional

import ccxt.async_support as ccxt

from market_data.models.candle import Candle


# Map our exchange identifiers to ccxt classes
EXCHANGE_NAME_MAP = {
    "binance": ccxt.binance,
    "bybit": ccxt.bybit,
    "mexc": ccxt.mexc,
}

# Maximum number of candles per API call (most exchanges support 1000)
MAX_LIMIT = 1000

# Number of retries on transient errors
MAX_RETRIES = 3

# Base delay (seconds) for exponential backoff
BASE_DELAY = 1.0


class HistoricalDownloader:
    """
    Downloads historical candle data from an exchange, handling pagination,
    retries, and rate limits.
    """

    def __init__(self, exchange_id: str = "default") -> None:
        self._exchange_id = exchange_id

    async def download_range(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Candle]:
        """
        Fetch all candles for the given exchange/symbol/timeframe between
        *start_time* and *end_time* (milliseconds, UTC).  If *start_time* is
        ``None``, the earliest available data is fetched.  If *end_time* is
        ``None``, data up to the present is fetched.

        Returns a list of :class:`Candle` objects sorted by timestamp.
        Always returns a list (possibly empty). Never returns None.
        """
        ex_id = exchange.lower()
        if ex_id not in EXCHANGE_NAME_MAP:
            print(f"Unsupported exchange: {exchange}")
            return []

        exchange_cls = EXCHANGE_NAME_MAP[ex_id]
        ex = exchange_cls()

        # Default to epoch if no start given
        since = start_time if start_time is not None else 0
        # Default to current time if no end given
        until = end_time if end_time is not None else self._now_ms()

        all_candles: List[Candle] = []

        try:
            while True:
                try:
                    candles_chunk = await self._fetch_with_retry(
                        ex, symbol, timeframe, since, until
                    )
                except Exception as e:
                    print(f"Download chunk failed: {e}")
                    break

                if not candles_chunk:
                    break

                # Convert raw OHLCV to Candle objects
                chunk = [
                    Candle(
                        timestamp=item[0],
                        open=item[1],
                        high=item[2],
                        low=item[3],
                        close=item[4],
                        volume=item[5],
                    )
                    for item in candles_chunk
                ]

                # Stop if we have passed the end_time
                if chunk[-1].timestamp > until:
                    # Keep only candles up to until
                    chunk = [c for c in chunk if c.timestamp <= until]
                    all_candles.extend(chunk)
                    break

                all_candles.extend(chunk)

                # Prepare next 'since' – use the last candle's timestamp + 1 ms
                last_ts = chunk[-1].timestamp
                since = last_ts + 1

                # If the chunk was smaller than the limit, we have reached the end
                if len(candles_chunk) < MAX_LIMIT:
                    break

                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.1)

        finally:
            await ex.close()

        # Remove any duplicates (should not happen, but be safe)
        seen = set()
        unique: List[Candle] = []
        for c in all_candles:
            if c.timestamp not in seen:
                seen.add(c.timestamp)
                unique.append(c)

        unique.sort(key=lambda c: c.timestamp)
        return unique

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _fetch_with_retry(
        self,
        ex: ccxt.Exchange,
        symbol: str,
        timeframe: str,
        since: int,
        until: int,
    ) -> List:
        """Fetch one page of OHLCV data with retry and rate‑limit handling."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                ohlcv = await ex.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=since,
                    limit=MAX_LIMIT,
                )
                return ohlcv
            except ccxt.RateLimitExceeded as e:
                # Respect the exchange's rate limit
                wait = getattr(ex, "rateLimit", 1000) / 1000  # ms -> seconds
                wait = max(wait, 1.0)
                await asyncio.sleep(wait)
                continue
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    continue
                raise  # Re-raise after exhausting retries
        return []  # Should not reach here

    @staticmethod
    def _now_ms() -> int:
        """Return current UTC time in milliseconds."""
        import time
        return int(time.time() * 1000)

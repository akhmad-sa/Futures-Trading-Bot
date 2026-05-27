"""
Historical data downloader with pagination, retry, and rate‑limit handling.

Fetches OHLCV candles from supported exchanges (Binance, Bybit, MEXC)
using the ccxt async library.  Designed to be used by the
:class:`MarketDataService` when local storage is missing or incomplete.
Supports exchange‑aware symbol normalisation via
:func:`market_data.normalization.symbols.normalize_symbol`.
"""

import asyncio
from typing import List, Optional
import logging

import ccxt.async_support as ccxt

from market_data.models.candle import Candle
from market_data.normalization.symbols import normalize_symbol


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

# Default lookback window (days) when no start_time is provided
DEFAULT_LOOKBACK_DAYS = 30
# Milliseconds in one day
_MS_PER_DAY = 86_400_000

logger = logging.getLogger(__name__)


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
        ``None``, a safe recent window of *DEFAULT_LOOKBACK_DAYS* days is used.
        If *end_time* is ``None``, data up to the present is fetched.

        *symbol* should be provided in canonical form (e.g. ``"BTCUSDT"``);
        it will be normalised automatically for the target exchange.

        Returns a list of :class:`Candle` objects sorted by timestamp.
        Always returns a list (possibly empty). Never returns None.
        """
        ex_id = exchange.lower()
        if ex_id not in EXCHANGE_NAME_MAP:
            logger.warning("Unsupported exchange: %s", exchange)
            return []

        # ── Normalise symbol ──────────────────────────────────────
        native_symbol = normalize_symbol(ex_id, symbol, market_type="perp")
        logger.info(
            "Normalised symbol: %s -> %s (exchange=%s, timeframe=%s)",
            symbol, native_symbol, exchange, timeframe,
        )

        exchange_cls = EXCHANGE_NAME_MAP[ex_id]
        ex = exchange_cls()

        # ── Configure futures/swap mode for MEXC ──────────────────
        if ex_id == "mexc":
            ex.options["defaultType"] = "swap"
            logger.debug("MEXC exchange configured for swap market.")

        # Validate exchange capabilities (symbol and timeframe)
        try:
            await ex.load_markets()
            if native_symbol not in ex.markets:
                logger.warning(
                    "Symbol %s not found in markets for %s (possible symbols: …)",
                    native_symbol, exchange,
                )
                await ex.close()
                return []
            if hasattr(ex, 'timeframes') and timeframe not in ex.timeframes:
                logger.warning(
                    "Timeframe %s not supported by %s", timeframe, exchange
                )
                await ex.close()
                return []
        except Exception as e:
            logger.warning("Could not load markets for %s: %s", exchange, e)
            # Continue anyway – ccxt will raise an appropriate error later.

        # ── Resolve time range ────────────────────────────────────
        now = self._now_ms()
        if start_time is not None:
            since = start_time
        else:
            since = now - (DEFAULT_LOOKBACK_DAYS * _MS_PER_DAY)
        until = end_time if end_time is not None else now

        logger.info(
            "Download range: exchange=%s, symbol=%s, timeframe=%s, "
            "resolved_since=%d, resolved_until=%d, default_lookback_days=%d",
            exchange, native_symbol, timeframe,
            since, until, DEFAULT_LOOKBACK_DAYS,
        )

        all_candles: List[Candle] = []

        try:
            chunk_count = 0
            while True:
                try:
                    candles_chunk = await self._fetch_with_retry(
                        ex, native_symbol, timeframe, since, until
                    )
                except Exception as e:
                    logger.error(
                        "Download chunk failed for %s %s %s: %s",
                        exchange, native_symbol, timeframe, e,
                    )
                    break

                if not candles_chunk:
                    logger.info("Empty chunk received – stopping pagination.")
                    break

                # ── Validate raw fetch response ───────────────────
                if not isinstance(candles_chunk, list):
                    logger.error(
                        "fetch_ohlcv returned non‑list type: %s", type(candles_chunk)
                    )
                    break
                for item in candles_chunk:
                    if not isinstance(item, (list, tuple)) or len(item) < 6:
                        logger.error(
                            "Invalid OHLCV item: %s (expected list of 6 elements)", item
                        )
                        break
                else:
                    # All items valid
                    pass

                logger.info(
                    "Raw fetch chunk %d: %d candles, first timestamp=%d",
                    chunk_count + 1, len(candles_chunk), candles_chunk[0][0],
                )

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
                    logger.info(
                        "Reached end_time; trimmed chunk to %d candles.", len(chunk)
                    )
                    break

                all_candles.extend(chunk)
                chunk_count += 1
                logger.info(
                    "Fetched chunk %d for %s %s %s (since=%d, until=%d, chunk_size=%d)",
                    chunk_count, exchange, native_symbol, timeframe,
                    since, until, len(chunk),
                )

                # Prepare next 'since'
                last_ts = chunk[-1].timestamp
                since = last_ts + 1

                # If the chunk was smaller than the limit, we have reached the end
                if len(candles_chunk) < MAX_LIMIT:
                    logger.info(
                        "Chunk smaller than limit (%d < %d) – stopping pagination.",
                        len(candles_chunk), MAX_LIMIT,
                    )
                    break

                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.1)

        finally:
            await ex.close()

        # ── Deduplication ─────────────────────────────────────────
        before_dedup = len(all_candles)
        seen = set()
        unique: List[Candle] = []
        for c in all_candles:
            if c.timestamp not in seen:
                seen.add(c.timestamp)
                unique.append(c)

        unique.sort(key=lambda c: c.timestamp)
        after_dedup = len(unique)
        removed = before_dedup - after_dedup
        if removed > 0:
            logger.warning(
                "Removed %d duplicate candles (before=%d, after=%d).",
                removed, before_dedup, after_dedup,
            )
        else:
            logger.info(
                "No duplicates found (total=%d).", after_dedup,
            )

        if after_dedup == 0:
            logger.warning(
                "All candles were removed during deduplication – possible timestamp bug."
            )

        logger.info(
            "Downloaded %d unique candles for %s %s %s",
            after_dedup, exchange, native_symbol, timeframe,
        )
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
        """Fetch one page of OHLCV data with retry and rate‑limit handling.

        Distinguishes retryable exceptions (network, rate limit) from
        non‑retryable ones (authentication, bad request) and raises
        the latter immediately.
        """
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
                wait = getattr(ex, "rateLimit", 1000) / 1000
                wait = max(wait, 1.0)
                logger.warning(
                    "Rate limit exceeded for %s %s %s, waiting %.1f s (attempt %d/%d)",
                    symbol, timeframe, ex.id, wait, attempt, MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                continue
            except ccxt.NetworkError as e:
                # Includes RequestTimeout, DDoSProtection
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Network error for %s %s %s: %s (attempt %d/%d, retrying in %.1f s)",
                        symbol, timeframe, ex.id, e, attempt, MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise  # Re-raise after exhausting retries
            except ccxt.ExchangeError as e:
                # Non‑retryable – log and re‑raise
                logger.error(
                    "Non‑retryable exchange error for %s %s %s: %s",
                    symbol, timeframe, ex.id, e,
                )
                raise
        return []  # Should not reach here

    @staticmethod
    def _now_ms() -> int:
        """Return current UTC time in milliseconds."""
        import time
        return int(time.time() * 1000)

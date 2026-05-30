import logging
from typing import List, Optional

import ccxt.async_support as ccxt

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider
from market_data.normalization.symbols import normalize_symbol

logger = logging.getLogger(__name__)

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
            logger.warning("Unsupported exchange: %s", exchange)
            return []

        # ── Normalise symbol ──────────────────────────────────────
        native_symbol = normalize_symbol(ex_id, symbol, market_type="perp")
        logger.info(
            "Normalised symbol: %s -> %s (exchange=%s)",
            symbol, native_symbol, exchange,
        )

        exchange_cls = EXCHANGE_NAME_MAP[ex_id]
        ex = exchange_cls()
        if ex_id == "mexc":
            ex.options["defaultType"] = "swap"
        try:
            # Validate symbol and timeframe (best-effort, non-blocking)
            try:
                await ex.load_markets()
                if native_symbol not in ex.markets:
                    logger.warning(
                        "Symbol %s not found in %s markets", native_symbol, exchange
                    )
                    return []
                if hasattr(ex, "timeframes") and timeframe not in ex.timeframes:
                    logger.warning(
                        "Timeframe %s not supported by %s", timeframe, exchange
                    )
                    return []
            except Exception as e:
                logger.warning("Could not validate markets for %s: %s", exchange, e)

            # Use start_time as 'since' if provided, otherwise fall back to 'since' argument
            use_since = start_time if start_time is not None else since
            ohlcv = await ex.fetch_ohlcv(
                symbol=native_symbol,
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
            logger.info(
                "Fetched %d live candles from %s %s %s",
                len(raw), exchange, native_symbol, timeframe,
            )
            return raw
        except Exception as e:
            logger.error(
                "Live data fetch failed for %s %s %s: %s",
                exchange, native_symbol, timeframe, e,
            )
            return []
        finally:
            await ex.close()

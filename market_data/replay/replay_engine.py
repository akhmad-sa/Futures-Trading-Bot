"""
Deterministic, event‑driven replay engine for backtesting.

Fetches historical candles through the centralized :class:`MarketDataService`
and yields them one by one in chronological order.  The engine can also
drive a strategy directly by calling a callback on each candle, allowing
strategies to remain unaware of the data source (live vs replay).
"""

from typing import AsyncGenerator, Callable, List, Optional

from market_data import MarketDataService
from market_data.models.candle import Candle


class ReplayEngine:
    """
    Replays historical candles sequentially.

    .. code-block:: python

        engine = ReplayEngine(market_data_service)
        async for candle in engine.replay("binance", "BTC/USDT", "1h"):
            await strategy.on_candle(candle)
    """

    def __init__(self, service: MarketDataService) -> None:
        self._service = service

    async def replay(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> AsyncGenerator[Candle, None]:
        """
        Yield :class:`Candle` objects one by one in ascending timestamp order.

        Parameters
        ----------
        exchange : str
            Exchange identifier (e.g. ``"binance"``).
        symbol : str
            Trading pair (e.g. ``"BTC/USDT"``).
        timeframe : str
            Candle timeframe (e.g. ``"1h"``, ``"5m"``).
        start_time : int, optional
            Start of the replay window (milliseconds, UTC).
        end_time : int, optional
            End of the replay window (milliseconds, UTC).

        Yields
        ------
        Candle
            Next candle in chronological order.
        """
        candles = await self._service.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        )

        for candle in candles:
            yield candle

    async def replay_with_callback(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        on_candle: Callable[[Candle], None],
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> None:
        """
        Replay every candle and pass it to the *on_candle* callback.

        This method is intended for cases where the strategy is called
        synchronously (not a coroutine) – for example, when the strategy
        merely logs or updates internal state.

        Parameters
        ----------
        exchange : str
            Exchange identifier.
        symbol : str
            Trading pair.
        timeframe : str
            Candle timeframe.
        on_candle : Callable[[Candle], None]
            Synchronous function invoked for each candle.
        start_time : int, optional
            Start timestamp.
        end_time : int, optional
            End timestamp.
        """
        async for candle in self.replay(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
        ):
            on_candle(candle)

    async def replay_multi(
        self,
        exchange: str,
        symbols: List[str],
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> AsyncGenerator[List[Candle], None]:
        """
        Replay multiple symbols in lockstep, yielding one list per
        candle index.  All symbols must share the same timeframe.

        .. warning::
            This is a convenience method; a proper multi‑symbol backtest
            should align candle timestamps precisely.  Currently it simply
            groups candles by their position index, assuming all symbols
            have the same number of candles for the requested range.

        Yields
        ------
        List[Candle]
            One candle per symbol at each chronological step.
        """
        tasks = [
            self._service.get_candles(
                exchange=exchange,
                symbol=sym,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
            for sym in symbols
        ]
        all_candles = await asyncio.gather(*tasks)

        # Determine the smallest length (all should be equal, but be safe)
        min_len = min(len(lst) for lst in all_candles)
        for idx in range(min_len):
            yield [lst[idx] for lst in all_candles]

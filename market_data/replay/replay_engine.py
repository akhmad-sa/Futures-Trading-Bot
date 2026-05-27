"""
Deterministic, event‑driven replay engine for backtesting.

Replays a pre‑loaded list of :class:`Candle` objects that have been
explicitly provided to the constructor.  The engine does **not** fetch
data from any exchange, parquet file, or :class:`MarketDataService`.
"""

from typing import AsyncGenerator, Callable, List, Optional

from market_data.models.candle import Candle


class ReplayEngine:
    """
    Replays historical candles sequentially from a user‑supplied list.

    .. code-block:: python

        candles = [ ... ]  # List[Candle]
        engine = ReplayEngine(candles)
        async for candle in engine.replay():
            await strategy.on_candle(candle)
    """

    def __init__(self, candles: List[Candle]) -> None:
        self._candles = candles[:]  # defensive copy to avoid shared mutable state

    async def replay(
        self,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> AsyncGenerator[Candle, None]:
        """
        Yield :class:`Candle` objects one by one in ascending timestamp order.

        Parameters
        ----------
        start_time : int, optional
            Start of the replay window (milliseconds, UTC).  Only candles whose
            ``timestamp >= start_time`` are yielded.
        end_time : int, optional
            End of the replay window (milliseconds, UTC).  Only candles whose
            ``timestamp <= end_time`` are yielded.

        Yields
        ------
        Candle
            Next candle in chronological order.
        """
        for candle in self._candles:
            if start_time is not None and candle.timestamp < start_time:
                continue
            if end_time is not None and candle.timestamp > end_time:
                continue
            yield candle

    async def replay_with_callback(
        self,
        on_candle: Callable[[Candle], None],
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> None:
        """
        Replay every candle and pass it to the *on_candle* callback.

        Parameters
        ----------
        on_candle : Callable[[Candle], None]
            Synchronous function invoked for each candle.
        start_time : int, optional
            Start timestamp.
        end_time : int, optional
            End timestamp.
        """
        async for candle in self.replay(
            start_time=start_time,
            end_time=end_time,
        ):
            on_candle(candle)

    async def replay_multi(
        self,
        symbols_candles: List[List[Candle]],
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> AsyncGenerator[List[Candle], None]:
        """
        Replay multiple candle lists in lockstep, yielding one list per
        candle index.  All lists must contain the same number of candles.

        .. warning::
            This is a convenience method; a proper multi‑symbol backtest
            should align candle timestamps precisely.

        Yields
        ------
        List[Candle]
            One candle per list at each chronological step.
        """
        # Determine the smallest length (all should be equal, but be safe)
        min_len = min(len(lst) for lst in symbols_candles) if symbols_candles else 0
        for idx in range(min_len):
            # Apply time‑range filtering individually
            row = []
            for lst in symbols_candles:
                c = lst[idx]
                if start_time is not None and c.timestamp < start_time:
                    continue
                if end_time is not None and c.timestamp > end_time:
                    continue
                row.append(c)
            if row:
                yield row

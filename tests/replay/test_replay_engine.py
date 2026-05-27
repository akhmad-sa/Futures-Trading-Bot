"""
Tests for the deterministic replay engine.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_data.replay.replay_engine import ReplayEngine


class TestReplayEngine:
    """Verify that the replay engine yields candles in order."""

    @pytest.mark.asyncio
    async def test_replay_sequential(self, sample_candles):
        """Replay yields candles one by one in chronological order."""
        engine = ReplayEngine(sample_candles)
        replayed: List[Candle] = []
        async for candle in engine.replay():
            replayed.append(candle)
        assert len(replayed) == len(sample_candles)
        for i in range(1, len(replayed)):
            assert replayed[i].timestamp > replayed[i - 1].timestamp

    @pytest.mark.asyncio
    async def test_replay_empty(self):
        """Replay with no candles yields nothing."""
        engine = ReplayEngine([])
        replayed: List[Candle] = []
        async for candle in engine.replay():
            replayed.append(candle)
        assert replayed == []

    @pytest.mark.asyncio
    async def test_replay_with_callback(self, sample_candles):
        """Callback receives each candle."""
        engine = ReplayEngine(sample_candles)
        received: List[Candle] = []

        def on_candle(candle: Candle) -> None:
            received.append(candle)

        await engine.replay_with_callback(on_candle=on_candle)
        assert len(received) == len(sample_candles)

    @pytest.mark.asyncio
    async def test_replay_time_range(self, sample_candles):
        """Replay respects start_time / end_time."""
        start_ts = sample_candles[2].timestamp
        end_ts = sample_candles[7].timestamp
        engine = ReplayEngine(sample_candles)
        replayed: List[Candle] = []
        async for candle in engine.replay(start_time=start_ts, end_time=end_ts):
            replayed.append(candle)
        assert len(replayed) == 6  # indices 2..7 inclusive
        for c in replayed:
            assert start_ts <= c.timestamp <= end_ts

    @pytest.mark.asyncio
    async def test_replay_multi(self, sample_candles):
        """Multi‑symbol replay yields lists of candles."""
        # Create a second list of identical candles
        second_list: List[Candle] = sample_candles[:]
        engine = ReplayEngine(sample_candles)
        count = 0
        async for candle_list in engine.replay_multi(
            symbols_candles=[sample_candles, second_list],
        ):
            assert len(candle_list) == 2
            for c in candle_list:
                assert isinstance(c, Candle)
            count += 1
        # Should have as many steps as the length of the lists
        assert count == len(sample_candles)

    @pytest.mark.asyncio
    async def test_defensive_copy(self, sample_candles):
        """Modifying the original list does not affect the engine."""
        original: List[Candle] = sample_candles[:]
        engine = ReplayEngine(original)
        # Mutate the original
        original.clear()
        replayed: List[Candle] = []
        async for candle in engine.replay():
            replayed.append(candle)
        assert len(replayed) == len(sample_candles)  # engine still has all candles

    @pytest.mark.asyncio
    async def test_replay_reset_between_runs(self, sample_candles):
        """Multiple replay runs yield the same candles."""
        engine = ReplayEngine(sample_candles)
        run1: List[Candle] = []
        run2: List[Candle] = []
        async for candle in engine.replay():
            run1.append(candle)
        async for candle in engine.replay():
            run2.append(candle)
        assert len(run1) == len(run2)
        for c1, c2 in zip(run1, run2):
            assert c1.timestamp == c2.timestamp

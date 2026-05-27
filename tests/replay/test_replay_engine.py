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
    async def test_replay_sequential(self, market_data_service, sample_candles):
        """Replay yields candles one by one in chronological order."""
        engine = ReplayEngine(market_data_service)
        replayed = []
        async for candle in engine.replay(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        ):
            replayed.append(candle)
        assert len(replayed) == len(sample_candles)
        for i in range(1, len(replayed)):
            assert replayed[i].timestamp > replayed[i - 1].timestamp

    @pytest.mark.asyncio
    async def test_replay_empty(self, empty_market_data_service):
        """Replay with no candles yields nothing."""
        engine = ReplayEngine(empty_market_data_service)
        replayed = []
        async for candle in engine.replay(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        ):
            replayed.append(candle)
        assert replayed == []

    @pytest.mark.asyncio
    async def test_replay_with_callback(self, market_data_service, sample_candles):
        """Callback receives each candle."""
        engine = ReplayEngine(market_data_service)
        received = []

        def on_candle(candle: Candle) -> None:
            received.append(candle)

        await engine.replay_with_callback(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            on_candle=on_candle,
        )
        assert len(received) == len(sample_candles)

    @pytest.mark.asyncio
    async def test_replay_multi(self, market_data_service, sample_candles):
        """Multi‑symbol replay yields lists of candles."""
        engine = ReplayEngine(market_data_service)
        symbols = ["BTC/USDT", "ETH/USDT"]
        count = 0
        async for candle_list in engine.replay_multi(
            exchange="binance",
            symbols=symbols,
            timeframe="1h",
        ):
            assert len(candle_list) == len(symbols)
            for c in candle_list:
                assert isinstance(c, Candle)
            count += 1
        # Should have as many steps as the smallest symbol's candle count
        assert count == len(sample_candles)

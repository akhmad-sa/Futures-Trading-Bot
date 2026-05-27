"""
Tests for the centralized MarketDataService.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_data.services.market_data_service import MarketDataService
from market_data.services.historical_data_provider import HistoricalDataProvider


class TestMarketDataService:
    """Verify MarketDataService behaviour."""

    @pytest.mark.asyncio
    async def test_get_candles_with_list(self, sample_candles):
        """Service initialised with a list returns those candles."""
        service = MarketDataService(provider=sample_candles)
        candles = await service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert len(candles) == len(sample_candles)
        assert candles[0].timestamp == sample_candles[0].timestamp

    @pytest.mark.asyncio
    async def test_get_candles_with_provider(self, market_data_service, sample_candles):
        """Service with a mock provider returns the provider's candles."""
        candles = await market_data_service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert len(candles) == len(sample_candles)

    @pytest.mark.asyncio
    async def test_get_candles_empty_provider(self, empty_market_data_service):
        """Service with an empty provider returns an empty list."""
        candles = await empty_market_data_service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert candles == []

    @pytest.mark.asyncio
    async def test_get_candles_no_provider(self):
        """Service with no provider raises RuntimeError."""
        service = MarketDataService(provider=None)
        with pytest.raises(RuntimeError, match="No data provider configured"):
            await service.get_candles(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
            )

    @pytest.mark.asyncio
    async def test_get_candles_with_time_range(self, market_data_service, sample_candles):
        """Service filters candles by start_time and end_time."""
        start_ts = sample_candles[2].timestamp
        end_ts = sample_candles[7].timestamp
        candles = await market_data_service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_time=start_ts,
            end_time=end_ts,
        )
        # Should return candles with timestamps in [start_ts, end_ts]
        for c in candles:
            assert start_ts <= c.timestamp <= end_ts
        # Should be a subset of the full list
        assert len(candles) <= len(sample_candles)

    @pytest.mark.asyncio
    async def test_store_and_replay_candles(self, market_data_service, sample_candles, tmp_path):
        """Store candles and replay them."""
        # Use a temporary directory to avoid polluting real data
        service = MarketDataService(
            provider=sample_candles,
            data_dir=str(tmp_path / "candles"),
        )
        await service.store_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            candles=sample_candles,
        )
        replayed = await service.replay_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert len(replayed) == len(sample_candles)
        assert replayed[0].timestamp == sample_candles[0].timestamp

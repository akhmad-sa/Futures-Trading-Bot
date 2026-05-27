"""
Tests for Parquet storage and loading in MarketDataService.
"""

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from market_data.models.candle import Candle
from market_data.services.market_data_service import MarketDataService
from market_data.services.historical_data_provider import HistoricalDataProvider


class TestParquetLoading:
    """Verify that candles are correctly stored and loaded from Parquet."""

    @pytest.mark.asyncio
    async def test_store_and_load_parquet(self, sample_candles, tmp_path):
        """Store candles to Parquet and load them back."""
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
        loaded = await service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert len(loaded) == len(sample_candles)
        for orig, loaded_c in zip(sample_candles, loaded):
            assert orig.timestamp == loaded_c.timestamp
            assert orig.open == loaded_c.open
            assert orig.high == loaded_c.high
            assert orig.low == loaded_c.low
            assert orig.close == loaded_c.close
            assert orig.volume == loaded_c.volume

    @pytest.mark.asyncio
    async def test_load_missing_file(self, tmp_path):
        """Loading from a non‑existent file returns empty list."""
        service = MarketDataService(
            provider=[],
            data_dir=str(tmp_path / "candles"),
        )
        loaded = await service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        assert loaded == []

    @pytest.mark.asyncio
    async def test_incremental_update(self, sample_candles, tmp_path):
        """Adding new candles merges correctly without duplicates."""
        service = MarketDataService(
            provider=sample_candles,
            data_dir=str(tmp_path / "candles"),
        )
        # Store first batch (first 5 candles)
        first_batch = sample_candles[:5]
        await service.store_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            candles=first_batch,
        )
        # Store second batch (all 10, overlapping)
        await service.store_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            candles=sample_candles,
        )
        loaded = await service.get_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
        )
        # Should have 10 unique candles
        assert len(loaded) == 10
        # Timestamps should be sorted
        timestamps = [c.timestamp for c in loaded]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_parquet_file_created(self, sample_candles, tmp_path):
        """Verify that the Parquet file is actually created on disk."""
        data_dir = tmp_path / "candles"
        service = MarketDataService(
            provider=sample_candles,
            data_dir=str(data_dir),
        )
        await service.store_candles(
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            candles=sample_candles,
        )
        expected_path = data_dir / "binance" / "BTC_USDT" / "1h.parquet"
        assert expected_path.exists()
        # Verify it's a valid Parquet file
        df = pd.read_parquet(expected_path)
        assert len(df) == len(sample_candles)

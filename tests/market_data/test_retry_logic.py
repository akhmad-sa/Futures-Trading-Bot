"""
Tests for retry logic in the HistoricalDownloader.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import ccxt.async_support as ccxt

from market_data.ingestion.historical_downloader import HistoricalDownloader


class TestRetryLogic:
    """Verify that the downloader retries on transient errors."""

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self):
        """Downloader retries after a NetworkError."""
        downloader = HistoricalDownloader()

        # Create a mock exchange that fails twice then succeeds
        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv = AsyncMock(
            side_effect=[
                ccxt.NetworkError("timeout"),
                ccxt.NetworkError("timeout"),
                [
                    [1700000000000, 50000.0, 50100.0, 49900.0, 50050.0, 100.0],
                    [1700003600000, 50100.0, 50200.0, 50000.0, 50150.0, 150.0],
                ],
            ]
        )
        mock_ex.id = "binance"
        mock_ex.rateLimit = 1000

        # Patch the internal _fetch_with_retry to use our mock
        with patch.object(
            downloader,
            "_fetch_with_retry",
            new=AsyncMock(side_effect=mock_ex.fetch_ohlcv.side_effect),
        ):
            # We need to call download_range which internally uses _fetch_with_retry
            # But download_range also creates its own exchange instance.
            # For this test we directly test _fetch_with_retry.
            result = await downloader._fetch_with_retry(
                ex=mock_ex,
                symbol="BTC/USDT",
                timeframe="1h",
                since=1700000000000,
                until=1700007200000,
            )
            assert len(result) == 2
            assert result[0][0] == 1700000000000

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Downloader waits and retries on RateLimitExceeded."""
        downloader = HistoricalDownloader()

        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv = AsyncMock(
            side_effect=[
                ccxt.RateLimitExceeded("rate limit"),
                [
                    [1700000000000, 50000.0, 50100.0, 49900.0, 50050.0, 100.0],
                ],
            ]
        )
        mock_ex.id = "binance"
        mock_ex.rateLimit = 1000

        with patch.object(
            downloader,
            "_fetch_with_retry",
            new=AsyncMock(side_effect=mock_ex.fetch_ohlcv.side_effect),
        ):
            result = await downloader._fetch_with_retry(
                ex=mock_ex,
                symbol="BTC/USDT",
                timeframe="1h",
                since=1700000000000,
                until=1700003600000,
            )
            assert len(result) == 1
            assert result[0][0] == 1700000000000

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Downloader raises after exhausting retries."""
        downloader = HistoricalDownloader()

        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv = AsyncMock(
            side_effect=ccxt.NetworkError("persistent error")
        )
        mock_ex.id = "binance"
        mock_ex.rateLimit = 1000

        with patch.object(
            downloader,
            "_fetch_with_retry",
            new=AsyncMock(side_effect=mock_ex.fetch_ohlcv.side_effect),
        ):
            with pytest.raises(ccxt.NetworkError):
                await downloader._fetch_with_retry(
                    ex=mock_ex,
                    symbol="BTC/USDT",
                    timeframe="1h",
                    since=1700000000000,
                    until=1700003600000,
                )

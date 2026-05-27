"""
Shared fixtures and configuration for the test suite.
"""

import asyncio
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from market_data.models.candle import Candle
from market_data.services.data_provider import DataProvider
from market_data.services.market_data_service import MarketDataService
from market_data.ingestion.historical_downloader import HistoricalDownloader


# ------------------------------------------------------------------
# Sample candle data for deterministic tests
# ------------------------------------------------------------------
@pytest.fixture
def sample_candles() -> List[Candle]:
    """Return a list of 10 deterministic candles (1h timeframe)."""
    base_ts = 1700000000000  # 2023-11-14T00:00:00 UTC
    candles = []
    for i in range(10):
        ts = base_ts + i * 3600_000  # 1 hour in ms
        candles.append(
            Candle(
                timestamp=ts,
                open=50000.0 + i * 10,
                high=50100.0 + i * 10,
                low=49900.0 + i * 10,
                close=50050.0 + i * 10,
                volume=100.0 + i * 5,
            )
        )
    return candles


@pytest.fixture
def empty_candles() -> List[Candle]:
    """Return an empty list of candles."""
    return []


# ------------------------------------------------------------------
# Mock data provider
# ------------------------------------------------------------------
class MockDataProvider(DataProvider):
    """A mock provider that returns pre‑defined candles."""

    def __init__(self, candles: List[Candle]) -> None:
        self._candles = candles

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
        # Simulate filtering by time range (simplified)
        result = self._candles
        if start_time is not None:
            result = [c for c in result if c.timestamp >= start_time]
        if end_time is not None:
            result = [c for c in result if c.timestamp <= end_time]
        return result


@pytest.fixture
def mock_provider(sample_candles) -> MockDataProvider:
    return MockDataProvider(sample_candles)


@pytest.fixture
def empty_provider() -> MockDataProvider:
    return MockDataProvider([])


# ------------------------------------------------------------------
# MarketDataService with mock provider
# ------------------------------------------------------------------
@pytest.fixture
def market_data_service(mock_provider: MockDataProvider) -> MarketDataService:
    return MarketDataService(provider=mock_provider)


@pytest.fixture
def empty_market_data_service(empty_provider: MockDataProvider) -> MarketDataService:
    return MarketDataService(provider=empty_provider)


# ------------------------------------------------------------------
# Mock HistoricalDownloader (to avoid real API calls)
# ------------------------------------------------------------------
@pytest.fixture
def mock_downloader(sample_candles):
    """Return a mock HistoricalDownloader that returns sample candles."""
    downloader = MagicMock(spec=HistoricalDownloader)
    downloader.download_range = AsyncMock(return_value=sample_candles)
    return downloader


# ------------------------------------------------------------------
# Async event loop fixture
# ------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

"""
Tests for candle normalization and conversion.
"""

import pytest

from market_data.models.candle import Candle


class TestCandleNormalization:
    """Verify that Candle objects are correctly constructed."""

    def test_candle_creation(self):
        """Create a Candle with valid data."""
        candle = Candle(
            timestamp=1700000000000,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.0,
        )
        assert candle.timestamp == 1700000000000
        assert candle.open == 50000.0
        assert candle.high == 50100.0
        assert candle.low == 49900.0
        assert candle.close == 50050.0
        assert candle.volume == 100.0

    def test_candle_negative_values(self):
        """Candle with negative values should be allowed (edge case)."""
        candle = Candle(
            timestamp=1700000000000,
            open=-1.0,
            high=0.0,
            low=-2.0,
            close=-0.5,
            volume=0.0,
        )
        assert candle.open == -1.0

    def test_candle_zero_volume(self):
        """Candle with zero volume is valid."""
        candle = Candle(
            timestamp=1700000000000,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=0.0,
        )
        assert candle.volume == 0.0

    def test_candle_timestamp_integer(self):
        """Timestamp must be an integer (milliseconds)."""
        candle = Candle(
            timestamp=1700000000000,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=100.0,
        )
        assert isinstance(candle.timestamp, int)

    def test_candle_from_ohlcv_list(self):
        """Convert a raw OHLCV list to a Candle."""
        ohlcv = [1700000000000, 50000.0, 50100.0, 49900.0, 50050.0, 100.0]
        candle = Candle(
            timestamp=ohlcv[0],
            open=ohlcv[1],
            high=ohlcv[2],
            low=ohlcv[3],
            close=ohlcv[4],
            volume=ohlcv[5],
        )
        assert candle.timestamp == ohlcv[0]
        assert candle.close == ohlcv[4]

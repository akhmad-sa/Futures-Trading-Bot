"""
Tests for breakout detection.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.trendline import Trendline
from market_structure.breakout import BreakoutDetector


def _make_candle(close: float, high: float = None, low: float = None,
                 timestamp: int = 1_700_000_000_000) -> Candle:
    """Helper to create a single candle."""
    return Candle(
        timestamp=timestamp,
        open=close,
        high=high or close,
        low=low or close,
        close=close,
        volume=100.0,
    )


class TestBreakoutDetection:
    """Verify breakout detection correctness."""

    def test_breakout_above_resistance(self):
        """Price closes above a falling resistance trendline."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        candle = _make_candle(close=80)  # at index 5, line price = 75
        detector = BreakoutDetector(confirmation_candles=1)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result == "above"

    def test_no_breakout_below_resistance(self):
        """Price closes below resistance line – not a breakout."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        candle = _make_candle(close=70)
        detector = BreakoutDetector(confirmation_candles=1)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result is None

    def test_breakout_below_support(self):
        """Price closes below a rising support trendline."""
        line = Trendline(is_support=True, x1=0, y1=50, x2=4, y2=70)
        candle = _make_candle(close=65)  # at index 5, line price = 75
        detector = BreakoutDetector(confirmation_candles=1)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result == "below"

    def test_confirmation_candles(self):
        """Require multiple closes beyond the line."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        detector = BreakoutDetector(confirmation_candles=2)
        candle1 = _make_candle(close=80, high=85, low=75)
        result1 = detector.check_breakout(candle1, line, candle_index=5)
        assert result1 is None
        candle2 = _make_candle(close=82, high=85, low=78)
        result2 = detector.check_breakout(candle2, line, candle_index=6)
        assert result2 == "above"

    def test_retest_confirmation(self):
        """Breakout requires a subsequent retest of the line."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        detector = BreakoutDetector(confirmation_candles=1, require_retest=True)
        candle1 = _make_candle(close=80)
        result1 = detector.check_breakout(candle1, line, candle_index=5)
        assert result1 is None
        candle2 = _make_candle(close=75.03)
        result2 = detector.check_breakout(candle2, line, candle_index=6)
        assert result2 is None  # retest observed
        candle3 = _make_candle(close=82)
        result3 = detector.check_breakout(candle3, line, candle_index=7)
        assert result3 == "above"

    def test_reset(self):
        """reset clears internal state."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        detector = BreakoutDetector(confirmation_candles=1)
        candle = _make_candle(close=80)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result == "above"
        detector.reset()
        result2 = detector.check_breakout(candle, line, candle_index=5)
        assert result2 == "above"

    def test_deterministic_replay(self):
        """Running breakout detection multiple times yields identical results."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        candles = [
            _make_candle(close=80, timestamp=1_700_000_000_005),
            _make_candle(close=82, timestamp=1_700_000_000_006),
        ]
        detector = BreakoutDetector(confirmation_candles=2)
        results1 = []
        for i, c in enumerate(candles):
            results1.append(detector.check_breakout(c, line, i + 5))
        detector.reset()
        results2 = []
        for i, c in enumerate(candles):
            results2.append(detector.check_breakout(c, line, i + 5))
        assert results1 == results2

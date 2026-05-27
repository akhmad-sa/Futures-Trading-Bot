"""
Tests for breakout detection.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.trendline import Trendline
from market_structure.breakout import BreakoutDetector


def _make_candle(close: float, high: float = None, low: float = None) -> Candle:
    """Helper to create a single candle."""
    return Candle(
        timestamp=1_700_000_000_000,
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
        # Resistance line from (0, 100) to (4, 80), slope = -5 per index
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        # At index 5, line price = 75
        candle = _make_candle(close=80)  # close above 75
        detector = BreakoutDetector(confirmation_candles=1)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result == "above"

    def test_no_breakout_below_resistance(self):
        """Price closes below resistance line – not a breakout (below is not above)."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        candle = _make_candle(close=70)
        detector = BreakoutDetector(confirmation_candles=1)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result is None

    def test_breakout_below_support(self):
        """Price closes below a rising support trendline."""
        line = Trendline(is_support=True, x1=0, y1=50, x2=4, y2=70)
        # At index 5, line price = 75
        candle = _make_candle(close=65)  # close below 75
        detector = BreakoutDetector(confirmation_candles=1)
        result = detector.check_breakout(candle, line, candle_index=5)
        assert result == "below"

    def test_confirmation_candles(self):
        """Require multiple closes beyond the line."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        detector = BreakoutDetector(confirmation_candles=2)
        # First candle above
        candle1 = _make_candle(close=80, high=85, low=75)
        result1 = detector.check_breakout(candle1, line, candle_index=5)
        assert result1 is None  # not yet confirmed
        # Second candle above
        candle2 = _make_candle(close=82, high=85, low=78)
        result2 = detector.check_breakout(candle2, line, candle_index=6)
        assert result2 == "above"

    def test_retest_confirmation(self):
        """Breakout requires a subsequent retest of the line."""
        line = Trendline(is_support=False, x1=0, y1=100, x2=4, y2=80)
        detector = BreakoutDetector(confirmation_candles=1, require_retest=True)
        # Breakout candle
        candle1 = _make_candle(close=80)
        result1 = detector.check_breakout(candle1, line, candle_index=5)
        assert result1 is None  # waiting for retest
        # Retest candle – close near line (76.8? tolerance 0.1% of line=0.075? line at 5 is 75, tolerance=0.075)
        # close=75.05 is within 0.075 of 75
        candle2 = _make_candle(close=75.03)
        result2 = detector.check_breakout(candle2, line, candle_index=6)
        assert result2 is None  # retest observed but not yet confirmed after retest
        # Third candle above again
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
        # After reset, same candle should trigger again
        result2 = detector.check_breakout(candle, line, candle_index=5)
        assert result2 == "above"

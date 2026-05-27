"""
Tests for pivot detection – repaint safety and determinism.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.pivots import detect_swing_highs, detect_swing_lows, detect_pivots


def _make_candles(close_prices: List[float], high_prices: List[float] = None,
                  low_prices: List[float] = None) -> List[Candle]:
    """Helper to create candles from prices."""
    highs = high_prices or close_prices
    lows = low_prices or [p * 0.99 for p in close_prices]
    candles = []
    for i in range(len(close_prices)):
        ts = 1_700_000_000_000 + i * 3_600_000
        candles.append(Candle(
            timestamp=ts,
            open=close_prices[i],
            high=highs[i],
            low=lows[i],
            close=close_prices[i],
            volume=100.0,
        ))
    return candles


class TestPivotDetection:
    """Verify that pivot detection works correctly and does not repaint."""

    def test_swing_high_simple(self):
        """Classic peak detection."""
        prices = [10, 20, 30, 25, 20, 15, 10]
        candles = _make_candles(prices)
        highs = detect_swing_highs(candles, left=1, right=1)
        assert highs == [2]  # index 2 is the highest

    def test_swing_low_simple(self):
        """Classic trough detection."""
        prices = [30, 20, 10, 15, 20, 25, 30]
        candles = _make_candles(prices)
        lows = detect_swing_lows(candles, left=1, right=1)
        assert lows == [2]  # index 2 is the lowest

    def test_no_pivot_at_edges(self):
        """Last 'right' candles should not be pivots (no future data)."""
        prices = [10, 20, 30, 25, 20, 15, 10]
        candles = _make_candles(prices)
        # right=2: last 2 indices (5,6) cannot be pivots
        highs = detect_swing_highs(candles, left=1, right=2)
        # index 2 has high 30, right side checks indices 3,4 (25,20) – ok.
        # index 3 has high 25, right side would check 4,5: 20<25, then 15<25 – both lower, so index 3 would also be a pivot? Verify logic.
        # Actually detect_swing_highs uses high >= price. For index 3: price=25, right side i+1=4 high=20<25 ok, i+2=5 high=15<25 ok. So index 3 qualifies. That's fine.
        # But index 4,5,6 cannot because no right side.
        for idx in highs:
            assert idx < len(candles) - 2  # right=2

    def test_repaint_safety(self):
        """Pivot at index i must have all right‑side candles closed."""
        # Create a scenario where a future candle would break the pivot
        candles = _make_candles([10, 30, 20, 10, 15])
        # left=1, right=1
        # index 1: high=30, left index 0=10<30 ok, right index 2=20<30 ok => pivot
        highs = detect_swing_highs(candles, left=1, right=1)
        assert highs == [1]
        # Add a new higher candle at the end – the old pivot should remain
        candles.append(Candle(
            timestamp=1_700_000_000_000 + 5 * 3_600_000,
            open=40, high=45, low=38, close=42, volume=100.0,
        ))
        # Re-run detection on the extended list – pivot at index 1 should still be valid
        highs2 = detect_swing_highs(candles, left=1, right=1)
        assert 1 in highs2  # still a pivot
        # New peak at index 5 is also a pivot (but not yet confirmed until more candles)
        # Since right=1, index 4 (the last with right data) is index 4? Let's compute:
        # n=6, right=1 => iterate i from left=1 to n-right-1=4 => indices 1..4.
        # index 4: price=10? actually prices: [10,30,20,10,15,42]
        # index 4 close=15, high? we set high=close? the helper sets high=close.
        # high=15, left candles index3=10<15 ok, right candle index5=42>=15 => not pivot.
        # index 5 cannot be considered because right=1, max i = n-right-1 = 4.
        # So new high 42 is not yet confirmed. Good – no repaint!

    def test_detect_pivots_combined(self):
        """detect_pivots returns combined sorted list."""
        candles = _make_candles([10, 20, 30, 25, 20, 15, 10, 18, 22])
        pivots = detect_pivots(candles, left=1, right=1)
        # indices: 2 high, 6 low (maybe also 8 high? but 8 is last index with right=1? n=9, max i=7, so 8 not considered)
        # let's compute quickly: highs should include 2; lows should include 6.
        types = {i: t for i, t in pivots}
        assert types.get(2) == "high"
        assert types.get(6) == "low"

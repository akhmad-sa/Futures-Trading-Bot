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

    def test_detect_pivots_combined(self):
        """detect_pivots returns combined sorted list."""
        candles = _make_candles([10, 20, 30, 25, 20, 15, 10, 18, 22])
        pivots = detect_pivots(candles, left=1, right=1)
        types = {i: t for i, t in pivots}
        assert types.get(2) == "high"
        assert types.get(6) == "low"

    def test_deterministic_replay(self):
        """Running pivot detection multiple times on same candles yields identical results."""
        candles = _make_candles([10, 20, 30, 25, 20, 15, 10, 18, 22])
        pivots1 = detect_pivots(candles, left=1, right=1)
        pivots2 = detect_pivots(candles, left=1, right=1)
        assert pivots1 == pivots2

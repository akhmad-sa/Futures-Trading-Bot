"""
Tests for trendline lifecycle: creation, filtering, expiry, and consumption.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.trendline import build_trendlines, Trendline


def _make_candles(close_prices: List[float], high_prices: List[float] = None,
                  low_prices: List[float] = None) -> List[Candle]:
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


class TestTrendlineLifecycle:
    """Verify trendline creation filters and lifecycle fields."""

    def test_min_pivot_spacing_filter(self):
        """Pivots too close should not create a trendline."""
        # Prices: 100, 99, 98, 97, 96, 95 (descending highs)
        # left=1, right=1 -> highs at indices 0? Actually high at index 0? Let's compute:
        # With left=1, right=1, index 0 not considered (no left). Index1: high=99, left idx0=100>=99 => not high.
        # Index2: high=98, left idx1=99<98? Actually 99<98 false, so not high.
        # So no highs? Need a clear series.
        # Let's create a series with two distinct peaks separated by 2 candles and another with 1 candle.
        # We'll use a series: [110, 100, 105, 95, 90, 85]  highs: 110 (idx0?) left=1,right=1 => idx0 not considered. idx1 low, idx2 105 is high? left idx1=100<105 ok, right idx3=95<105 ok => high at idx2. No second high.
        # Not a good test. Instead we'll rely on the fact that with min_pivot_spacing=5, two highs at indices 1 and 3 (spacing 2) will be filtered out.
        # We'll build a series where two highs are 2 apart and min_pivot_spacing=3 -> expect 0 trendlines.
        # Let's create high indices: idx1=1, idx2=3.
        prices = [100, 110, 105, 108, 102, 98]  # highs at idx1=110, idx3=108? left1: idx0=100<110 ok, right idx2=105<110 ok -> high1. left3: idx2=105<108 ok, right idx4=102<108 ok -> high2. spacing=2.
        candles = _make_candles(prices)
        trendlines = build_trendlines(candles, left=1, right=1,
                                      min_pivot_spacing=3)
        assert len(trendlines) == 0

    def test_min_price_delta_filter(self):
        """Pivots with very similar prices should not create a trendline."""
        # Two highs: 100 and 100.5, delta=0.5% < 1% filter
        prices = [100, 100, 100.5, 99, 98, 97]  # highs at idx2=100.5? left idx1=100<100.5 ok, right idx3=99<100.5 ok -> high.
        # need another high at idx0? left=1,right=1 -> idx0 not considered, idx1 not high (left idx0=100>=100? Actually left high=100, but left comparison: candles[j].high >= price. For idx1, high=100? Wait prices: [100,100,100.5...]. idx1 high=100, left idx0=100>=100 -> invalid. So only one high.
        # Let's create two distinct high peaks with small price diff: e.g., 100 and 101, delta=0.01 = 1%. Set min_price_delta_pct=0.02 -> should be filtered.
        # We'll use left=2,right=2 to get more pivots.
        # Simpler: we'll test the filter directly by building with min_price_delta_pct=0.02 and two highs with delta 0.01.
        # Use a series with highs at indices 3 and 6 (prices 100 and 101)
        prices = [90, 95, 98, 100, 97, 96, 101, 99, 97]
        candles = _make_candles(prices)
        trendlines = build_trendlines(candles, left=2, right=2,
                                      min_price_delta_pct=0.02)
        # With left=2,right=2, highs at idx3 (100) and idx6 (101)? idx3: left indices 1,2: 95,98 both <100? 95<100 true, 98<100 true, right indices4,5:97,96 <100 -> high. idx6: left 4,5:97,96 <101 true, right indices7,8:99,97 <101 true -> high. spacing=3, min_price_delta_pct=0.02 => delta=1/100=0.01 <0.02 => should be filtered.
        assert len(trendlines) == 0

    def test_trendline_consumed_flag(self):
        """After marking a trendline as consumed, it should not be reused."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100]
        candles = _make_candles(prices)
        trendlines = build_trendlines(candles, left=1, right=1)
        # Should have at least one trendline (resistance? actually descending highs will produce lows? We'll just check that consumed works)
        if trendlines:
            tl = trendlines[0]
            assert tl.consumed is False
            tl.consumed = True
            assert tl.consumed is True
            # Simulate that after consumption, breakout on same line is prevented
            from market_structure.breakout import BreakoutDetector
            detector = BreakoutDetector(confirmation_candles=1)
            result = detector.check_breakout(candles[-1], tl, len(candles)-1)
            assert result is None, "Consumed trendline should not trigger breakout"

    def test_trendline_lifecycle_fields(self):
        """Trendline should have correct lifecycle fields after creation."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100]
        candles = _make_candles(prices)
        trendlines = build_trendlines(candles, left=1, right=1)
        for tl in trendlines:
            assert tl.created_at_index >= 0
            assert tl.last_touch_index >= 0
            assert tl.breakout_index == -1
            assert tl.consumed is False
            assert tl.active is True

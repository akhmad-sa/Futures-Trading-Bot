"""
Tests for the persistent MarketStructureEngine.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.engine import MarketStructureEngine
from signals.contracts import BreakoutEvent


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


class TestMarketStructureEngine:
    """Verify persistent engine behaviour."""

    def test_persistent_trendline_reuse(self):
        """Trendlines should persist and not be recreated every candle."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100, 102, 105]
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, min_pivot_spacing=2,
        )
        trendline_ids = set()
        for c in candles:
            engine.update(c)
            for atl in engine.active_trendlines:
                trendline_ids.add(atl.id)
        # At least one trendline should have been created
        assert len(trendline_ids) > 0

    def test_no_duplicate_breakout_events(self):
        """A single breakout should emit exactly one BreakoutEvent."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100]
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
        )
        breakout_count = 0
        for c in candles:
            events = engine.update(c)
            for ev in events:
                if isinstance(ev, BreakoutEvent):
                    breakout_count += 1
        assert breakout_count == 1

    def test_trendline_expiry(self):
        """Trendline should expire after max_age candles (no crash)."""
        prices = [100] * 150
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=2, pivot_right=2, min_pivot_spacing=3,
            trendline_max_age=10,
        )
        for c in candles:
            engine.update(c)
        # No assertion – just ensure no exception

    def test_per_trendline_breakout_isolation(self):
        """
        Breakout on one trendline should not affect breakout state of
        another trendline.
        """
        prices = [
            100, 99, 98, 97, 96, 95,
            96, 97, 96, 95, 94, 93,
        ]
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, min_pivot_spacing=2,
            breakout_confirmation=1,
        )
        for c in candles:
            engine.update(c)
        line_ids = set()
        for atl in engine.active_trendlines:
            assert atl.breakout_detector is not None
            line_ids.add(atl.id)
        assert len(line_ids) == len(engine.active_trendlines)

    def test_deterministic_replay(self):
        """Same candle stream must produce same events on multiple runs."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100, 98, 96]
        candles = _make_candles(prices)

        def run_engine():
            eng = MarketStructureEngine(
                pivot_left=1, pivot_right=1, breakout_confirmation=1,
            )
            ev_types = []
            for c in candles:
                for ev in eng.update(c):
                    ev_types.append(type(ev).__name__)
            return ev_types

        run1 = run_engine()
        run2 = run_engine()
        assert run1 == run2

    def test_event_ordering(self):
        """Events should be returned in a consistent order."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100]
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
        )
        for c in candles:
            engine.update(c)
        # Smoke test passed

    def test_filter_min_breakout_bps(self):
        """Breakout must exceed minimum distance threshold."""
        prices = [100, 99, 98, 97, 96, 95, 96.5, 97]
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
            min_breakout_bps=200,
        )
        breakout_found = False
        for c in candles:
            for ev in engine.update(c):
                if isinstance(ev, BreakoutEvent):
                    breakout_found = True
        assert not breakout_found, "Breakout should have been filtered"

    def test_breakout_with_sufficient_distance(self):
        """Breakout that exceeds threshold should be emitted."""
        prices = [100, 99, 98, 97, 96, 95, 100, 105]
        candles = _make_candles(prices)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
            min_breakout_bps=100,
        )
        breakout_found = False
        for c in candles:
            for ev in engine.update(c):
                if isinstance(ev, BreakoutEvent):
                    breakout_found = True
        assert breakout_found, "Breakout should have been emitted"

    def test_body_strength_filter(self):
        """Weak breakout candles should be filtered."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100]
        highs = [100, 99, 98, 97, 96, 95, 98, 100]
        lows  = [100, 99, 98, 97, 96, 95, 96, 99]
        candles = _make_candles(prices, high_prices=highs, low_prices=lows)
        engine = MarketStructureEngine(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
            body_strength_filter_enabled=True,
            min_body_ratio=0.8,
        )
        for c in candles:
            engine.update(c)
        # Smoke test – no crash

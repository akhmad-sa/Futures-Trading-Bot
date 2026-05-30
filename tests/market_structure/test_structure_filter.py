"""
Tests for optional HH/HL/LH/LL structure filter on channel strategy.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.swing_structure import TrendStructure
from strategy.implementations.trendline_breakout import TrendlineBreakoutStrategy


def _make_candles(close_prices: List[float]) -> List[Candle]:
    candles = []
    for i, close in enumerate(close_prices):
        candles.append(
            Candle(
                timestamp=1_700_000_000_000 + i * 3_600_000,
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000.0,
            )
        )
    return candles


class TestStructureFilterOnChannel:
    def test_strategy_filter_logic(self):
        strategy = TrendlineBreakoutStrategy(require_structure_filter=True)
        strategy._engine._structure.trend = TrendStructure.UPTREND
        assert strategy._structure_allows("long")
        assert not strategy._structure_allows("short")

        strategy._engine._structure.trend = TrendStructure.DOWNTREND
        assert strategy._structure_allows("short")
        assert not strategy._structure_allows("long")

    @pytest.mark.asyncio
    async def test_long_blocked_when_filter_on_and_neutral(self):
        strategy = TrendlineBreakoutStrategy(require_structure_filter=True)
        strategy._engine._structure.trend = TrendStructure.NEUTRAL
        strategy._engine.wait_bull_retest = False

        # Simulate retest signal path by forcing internal state after fake retest
        strategy._position = None
        # Manually invoke what would happen on bull_retest
        ch = strategy._engine.update(_make_candles([100, 101]))
        strategy._engine.wait_bull_retest = True
        # Patch: directly test filter on long signal path
        assert not strategy._structure_allows("long")

"""
Tests for multi-timeframe market structure (HTF bias filter).
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from market_structure.mtf import (
    MultiTimeframeConfig,
    MarketStructureContext,
    StructureFeed,
)
from market_structure.swing_structure import TrendStructure
from market_structure.timeframes import (
    get_interval_ms,
    is_higher_timeframe,
    suggest_structure_timeframe,
)
from strategy.implementations.trendline_breakout import TrendlineBreakoutStrategy


def _make_candles(
    close_prices: List[float],
    interval_ms: int = 3_600_000,
) -> List[Candle]:
    candles = []
    for i, close in enumerate(close_prices):
        candles.append(
            Candle(
                timestamp=1_700_000_000_000 + i * interval_ms,
                open=close,
                high=close + 2,
                low=close - 2,
                close=close,
                volume=1000.0,
            )
        )
    return candles


class TestTimeframes:
    def test_interval_ms(self):
        assert get_interval_ms("15m") == 900_000
        assert get_interval_ms("1h") == 3_600_000

    def test_is_higher_timeframe(self):
        assert is_higher_timeframe("1h", "15m")
        assert not is_higher_timeframe("15m", "1h")

    def test_suggest_structure_timeframe(self):
        assert suggest_structure_timeframe("15m") == "1h"
        assert suggest_structure_timeframe("5m") == "1h"


class TestMultiTimeframeConfig:
    def test_active_when_htf_differs(self):
        cfg = MultiTimeframeConfig("15m", "1h", enabled=True)
        assert cfg.is_active

    def test_inactive_when_same_tf(self):
        cfg = MultiTimeframeConfig("15m", "15m", enabled=True)
        assert not cfg.is_active

    def test_inactive_when_disabled(self):
        cfg = MultiTimeframeConfig("15m", "1h", enabled=False)
        assert not cfg.is_active

    def test_resolve_from_config(self):
        class FakeConfig:
            timeframe = "15m"
            structure_timeframe = "4h"
            structure_mtf_enabled = True

        cfg = MultiTimeframeConfig.resolve(FakeConfig())
        assert cfg.strategy_timeframe == "15m"
        assert cfg.structure_timeframe == "4h"
        assert cfg.is_active


class TestStructureFeed:
    def test_sync_no_look_ahead(self):
        htf = _make_candles([100, 105, 110, 108, 112], interval_ms=3_600_000)
        mtf = MultiTimeframeConfig("15m", "1h")
        feed = StructureFeed(mtf, pivot_len=1, tolerance_bps=0.0)
        feed._htf_candles = htf

        feed.sync_to(htf[0].timestamp)
        assert feed._htf_idx == 1

        feed.sync_to(htf[2].timestamp)
        assert feed._htf_idx == 3
        assert feed.state.effective_trend in (
            TrendStructure.UPTREND,
            TrendStructure.DOWNTREND,
            TrendStructure.NEUTRAL,
        )

    def test_strategy_uses_htf_override(self):
        strategy = TrendlineBreakoutStrategy(require_structure_filter=True)
        strategy._engine._structure.trend = TrendStructure.DOWNTREND
        strategy.set_structure_trend(TrendStructure.UPTREND)
        assert strategy._structure_allows("long")
        assert not strategy._structure_allows("short")


class TestMarketStructureContext:
    def test_uptrend_from_hh_hl_sequence(self):
        ctx = MarketStructureContext(pivot_len=1)
        prices = [100, 110, 105, 115, 110, 120]
        candles = _make_candles(prices, interval_ms=3_600_000)
        for i in range(len(candles)):
            ctx.update(candles[: i + 1])
        assert ctx.trend in (TrendStructure.UPTREND, TrendStructure.NEUTRAL)

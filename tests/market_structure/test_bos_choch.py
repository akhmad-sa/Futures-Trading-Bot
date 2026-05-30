"""
Tests for BOS / CHoCH structure break detection.
"""

from market_structure.bos_choch import (
    StructureBreakKind,
    StructureBreakTracker,
    StructureState,
    classify_break,
)
from market_structure.mtf import MarketStructureContext
from market_structure.swing_structure import TrendStructure
from market_data.models.candle import Candle


class TestClassifyBreak:
    def test_bos_bullish_from_neutral(self):
        assert classify_break("bullish", TrendStructure.NEUTRAL) == StructureBreakKind.BOS_BULLISH

    def test_choch_bullish_from_downtrend(self):
        assert classify_break("bullish", TrendStructure.DOWNTREND) == StructureBreakKind.CHOCH_BULLISH

    def test_choch_bearish_from_uptrend(self):
        assert classify_break("bearish", TrendStructure.UPTREND) == StructureBreakKind.CHOCH_BEARISH

    def test_bos_bearish_from_downtrend(self):
        assert classify_break("bearish", TrendStructure.DOWNTREND) == StructureBreakKind.BOS_BEARISH


class TestStructureBreakTracker:
    def _tracker_with_swings(self) -> StructureBreakTracker:
        t = StructureBreakTracker()
        t.on_swing_low(1, 90.0, 1000)
        t.on_swing_high(3, 100.0, 3000)
        return t

    def test_bos_bullish_on_high_break(self):
        t = self._tracker_with_swings()
        events = t.on_candle_close(4, close=101.0, high=102.0, low=99.0, timestamp_ms=4000)
        assert len(events) == 1
        assert events[0].kind == StructureBreakKind.BOS_BULLISH
        assert t.bias == TrendStructure.UPTREND

    def test_bos_bearish_on_low_break(self):
        t = self._tracker_with_swings()
        events = t.on_candle_close(4, close=89.0, high=91.0, low=88.0, timestamp_ms=4000)
        assert len(events) == 1
        assert events[0].kind == StructureBreakKind.BOS_BEARISH
        assert t.bias == TrendStructure.DOWNTREND

    def test_choch_bearish_after_uptrend_established(self):
        t = self._tracker_with_swings()
        t.on_candle_close(4, close=101.0, high=102.0, low=99.0, timestamp_ms=4000)
        t.on_swing_low(5, 95.0, 5000)
        events = t.on_candle_close(6, close=94.0, high=96.0, low=93.0, timestamp_ms=6000)
        assert len(events) == 1
        assert events[0].kind == StructureBreakKind.CHOCH_BEARISH
        assert t.bias == TrendStructure.DOWNTREND

    def test_choch_bullish_after_downtrend_established(self):
        t = self._tracker_with_swings()
        t.on_candle_close(4, close=89.0, high=91.0, low=88.0, timestamp_ms=4000)
        t.on_swing_high(5, 95.0, 5000)
        events = t.on_candle_close(6, close=96.0, high=97.0, low=94.0, timestamp_ms=6000)
        assert len(events) == 1
        assert events[0].kind == StructureBreakKind.CHOCH_BULLISH
        assert t.bias == TrendStructure.UPTREND

    def test_no_duplicate_break_on_same_swing(self):
        t = self._tracker_with_swings()
        t.on_candle_close(4, close=101.0, high=102.0, low=99.0, timestamp_ms=4000)
        again = t.on_candle_close(5, close=102.0, high=103.0, low=100.0, timestamp_ms=5000)
        assert again == []


class TestStructureState:
    def test_effective_trend_prefers_bias(self):
        state = StructureState(
            trend=TrendStructure.NEUTRAL,
            bias=TrendStructure.UPTREND,
        )
        assert state.effective_trend == TrendStructure.UPTREND
        assert state.allows_long()
        assert not state.allows_short()

    def test_effective_trend_falls_back_to_hh_hl(self):
        state = StructureState(
            trend=TrendStructure.DOWNTREND,
            bias=TrendStructure.NEUTRAL,
        )
        assert state.effective_trend == TrendStructure.DOWNTREND

    def test_blocks_long_on_bearish_choch(self):
        from market_structure.bos_choch import StructureBreakKind, StructureBreakEvent

        brk = StructureBreakEvent(
            kind=StructureBreakKind.CHOCH_BEARISH,
            candle_index=10,
            close_price=95.0,
            broken_level=98.0,
            broken_swing_index=5,
            broken_swing_type="low",
            timestamp_ms=5000,
            bias_after=TrendStructure.DOWNTREND,
        )
        state = StructureState(
            trend=TrendStructure.UPTREND,
            bias=TrendStructure.DOWNTREND,
            last_break=brk,
        )
        assert state.blocks_long_entry()
        assert not state.blocks_short_entry()

    def test_choch_exit_long_only_after_entry(self):
        from market_structure.bos_choch import StructureBreakKind, StructureBreakEvent

        brk = StructureBreakEvent(
            kind=StructureBreakKind.CHOCH_BEARISH,
            candle_index=10,
            close_price=95.0,
            broken_level=98.0,
            broken_swing_index=5,
            broken_swing_type="low",
            timestamp_ms=5000,
            bias_after=TrendStructure.DOWNTREND,
        )
        state = StructureState(
            trend=TrendStructure.UPTREND,
            bias=TrendStructure.DOWNTREND,
            last_break=brk,
        )
        assert not state.choch_exits_long(6000)
        assert state.choch_exits_long(4000)


class TestMarketStructureContextBosChoch:
    def test_context_emits_break_events(self):
        candles = []
        prices = [100, 102, 98, 105, 103, 95]
        for i, close in enumerate(prices):
            candles.append(
                Candle(
                    timestamp=1_700_000_000_000 + i * 3_600_000,
                    open=close,
                    high=close + 3,
                    low=close - 3,
                    close=close,
                    volume=1000.0,
                )
            )

        ctx = MarketStructureContext(pivot_len=1, use_bos_choch=True)
        for i in range(len(candles)):
            ctx.update(candles[: i + 1])

        assert ctx.break_tracker.bias in (
            TrendStructure.UPTREND,
            TrendStructure.DOWNTREND,
            TrendStructure.NEUTRAL,
        )

    def test_bos_disabled_skips_break_tracker(self):
        ctx = MarketStructureContext(pivot_len=1, use_bos_choch=False)
        candle = Candle(
            timestamp=1_700_000_000_000,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1000.0,
        )
        ctx.update([candle])
        assert ctx.break_tracker.bias == TrendStructure.NEUTRAL
        assert ctx.last_break_events == []

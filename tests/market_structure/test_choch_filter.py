"""Tests for CHoCH entry block and exit signals in trendline_breakout."""

import pytest

from market_structure.bos_choch import (
    StructureBreakKind,
    StructureBreakEvent,
    StructureState,
)
from market_structure.swing_structure import TrendStructure
from strategy.implementations.trendline_breakout import TrendlineBreakoutStrategy


def _choch_bearish_state(ts: int = 5000) -> StructureState:
    brk = StructureBreakEvent(
        kind=StructureBreakKind.CHOCH_BEARISH,
        candle_index=10,
        close_price=95.0,
        broken_level=98.0,
        broken_swing_index=5,
        broken_swing_type="low",
        timestamp_ms=ts,
        bias_after=TrendStructure.DOWNTREND,
    )
    return StructureState(
        trend=TrendStructure.UPTREND,
        bias=TrendStructure.DOWNTREND,
        last_break=brk,
    )


class TestChochEntryBlock:
    def test_blocks_long_on_counter_choch(self):
        strategy = TrendlineBreakoutStrategy(
            require_structure_filter=False,
            block_entry_on_counter_choch=True,
        )
        state = _choch_bearish_state()
        assert not strategy._structure_allows("long", state)
        assert strategy.entry_blocked_by_choch("long", state)

    def test_allows_short_on_bearish_choch(self):
        strategy = TrendlineBreakoutStrategy(
            require_structure_filter=False,
            block_entry_on_counter_choch=True,
        )
        state = _choch_bearish_state()
        assert strategy._structure_allows("short", state)

    def test_block_disabled(self):
        strategy = TrendlineBreakoutStrategy(
            require_structure_filter=False,
            block_entry_on_counter_choch=False,
        )
        state = _choch_bearish_state()
        assert strategy._structure_allows("long", state)


class TestChochExit:
    @pytest.mark.asyncio
    async def test_exit_long_on_counter_choch(self):
        class Cfg:
            structure_choch_exit_enabled = True
            structure_use_bos_choch = True
            use_trend_exit = False

        strategy = TrendlineBreakoutStrategy(
            config=Cfg(),
            choch_exit_enabled=True,
            min_hold_bars=1,
        )
        strategy._position = "long"
        strategy._entry_candle = 0
        strategy._entry_timestamp_ms = 1000
        strategy.set_structure_state(_choch_bearish_state(ts=5000))

        from market_data.models.candle import Candle

        candles = [
            Candle(
                timestamp=1000, open=100, high=101, low=99, close=100, volume=1.0
            ),
            Candle(
                timestamp=2000, open=100, high=101, low=94, close=95, volume=1.0
            ),
        ]
        sig = await strategy.get_exit_signal("BTCUSDT", candles)
        assert sig == "close"
        assert strategy.last_exit_reason == "choch_exit"

    @pytest.mark.asyncio
    async def test_no_exit_when_disabled(self):
        strategy = TrendlineBreakoutStrategy(
            choch_exit_enabled=False,
            min_hold_bars=1,
        )
        strategy._position = "long"
        strategy._entry_candle = 0
        strategy._entry_timestamp_ms = 1000
        strategy.set_structure_state(_choch_bearish_state(ts=5000))

        from market_data.models.candle import Candle

        candles = [
            Candle(
                timestamp=1000, open=100, high=101, low=99, close=100, volume=1.0
            ),
            Candle(
                timestamp=2000, open=100, high=101, low=94, close=95, volume=1.0
            ),
        ]
        sig = await strategy.get_exit_signal("BTCUSDT", candles)
        assert sig == "hold"

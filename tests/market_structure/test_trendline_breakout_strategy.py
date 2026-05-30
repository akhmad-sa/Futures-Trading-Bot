"""
Tests for Pine-style trendline breakout strategy (entry only).
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from strategy.implementations.trendline_breakout import TrendlineBreakoutStrategy
from risk.manager import RiskManager, RiskConfig
from risk.exit_levels import EntryRiskHints


def _make_candles(specs: List[dict]) -> List[Candle]:
    candles = []
    for i, s in enumerate(specs):
        close = s["close"]
        open_ = s.get("open", close)
        high = s.get("high", max(open_, close) + 1)
        low = s.get("low", min(open_, close) - 1)
        candles.append(
            Candle(
                timestamp=1_700_000_000_000 + i * 3_600_000,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=s.get("volume", 1000.0),
            )
        )
    return candles


class TestTrendlineBreakoutStrategy:
    @pytest.mark.asyncio
    async def test_entry_sets_hints_not_tp_sl(self):
        strategy = TrendlineBreakoutStrategy(
            pivot_len=1,
            vol_sma_period=3,
            vol_multiplier=0.5,
            require_structure_filter=False,
            require_confirmed_structure=False,
            allow_pending_structure=True,
            min_signal_score=0,
        )
        series = _make_candles(
            [
                {"close": 110, "high": 110, "low": 108},
                {"close": 105, "high": 105, "low": 103},
                {"close": 100, "high": 100, "low": 98},
                {"close": 98, "high": 99, "low": 97},
                {"close": 97, "high": 98, "low": 96},
                {"close": 96, "high": 97, "low": 95},
                {"close": 95, "high": 96, "low": 94},
                {"close": 96, "high": 97, "low": 95},
                {"close": 101, "open": 100, "high": 102, "low": 99, "volume": 5000},
                {"close": 102, "open": 100, "high": 103, "low": 100, "volume": 1000},
            ]
        )
        signals = []
        for i in range(len(series)):
            signals.append(await strategy.get_signal("TEST", series[: i + 1]))

        assert "long" in signals
        assert strategy.last_entry_hints is not None
        assert strategy.last_entry_hints.stop_anchor is not None
        assert not hasattr(strategy, "_take_profit")

    @pytest.mark.asyncio
    async def test_trend_exit_when_enabled(self):
        class Cfg:
            use_trend_exit = True

        strategy = TrendlineBreakoutStrategy(config=Cfg(), require_structure_filter=False)
        strategy._position = "long"
        strategy._entry_candle = 0
        candles = _make_candles(
            [{"close": 95, "open": 97, "low": 94, "high": 97, "volume": 1000}] * 5
        )
        strategy._engine.update(candles)
        signal = await strategy.get_signal("TEST", candles)
        assert signal in ("hold", "close")

    @pytest.mark.asyncio
    async def test_on_position_closed_clears_state(self):
        strategy = TrendlineBreakoutStrategy()
        strategy._position = "long"
        strategy.on_position_closed("stop_loss")
        assert strategy._position is None

    @pytest.mark.asyncio
    async def test_cooldown_blocks_rapid_reentry(self):
        strategy = TrendlineBreakoutStrategy(
            pivot_len=1,
            vol_sma_period=3,
            vol_multiplier=0.5,
            require_structure_filter=False,
            cooldown_after_trade_candles=5,
        )
        series = _make_candles(
            [{"close": 100 + i * 0.1, "open": 100, "high": 101, "low": 99} for i in range(12)]
        )
        strategy._last_trade_candle = 10
        signal = await strategy.get_signal("TEST", series)
        assert signal == "hold"

    def test_risk_manager_owns_tp_sl(self):
        rm = RiskManager(RiskConfig(take_profit_rr=3.0))
        state = rm.create_exit_state(
            "long",
            100.0,
            hints=EntryRiskHints(stop_anchor=98.0, atr_value=1.5),
            entry_bar_index=0,
        )
        assert state.take_profit > 100.0
        assert state.stop_loss < 100.0

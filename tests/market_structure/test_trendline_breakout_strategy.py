"""
Tests for the trendline breakout strategy.
"""

import pytest
from typing import List

from market_data.models.candle import Candle
from strategy.implementations.trendline_breakout import TrendlineBreakoutStrategy


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


class TestTrendlineBreakoutStrategy:
    """Verify trendline breakout strategy behavior."""

    @pytest.mark.asyncio
    async def test_bullish_breakout(self):
        """
        Price series that forms a descending resistance trendline
        and then breaks above it.
        """
        # Prices: 100, 99, 98, 97, 96, 95 (descending)
        # Then breakout: 97, 100 (close above resistance)
        prices = [100, 99, 98, 97, 96, 95, 97, 100]
        candles = _make_candles(prices)
        strategy = TrendlineBreakoutStrategy(
            pivot_left=1,
            pivot_right=1,
            breakout_confirmation=1,
        )
        signals = []
        for i in range(len(candles)):
            signal = await strategy.get_signal("TEST", candles[: i + 1])
            signals.append(signal)
        # Last signal should be "long"
        assert signals[-1] == "long", f"Expected long, got {signals[-1]}"

    @pytest.mark.asyncio
    async def test_bearish_breakdown(self):
        """
        Price series that forms an ascending support trendline
        and then breaks below it.
        """
        # Prices: 100, 101, 102, 103, 104, 105 (ascending)
        # Then breakdown: 103, 100 (close below support)
        prices = [100, 101, 102, 103, 104, 105, 103, 100]
        candles = _make_candles(prices)
        strategy = TrendlineBreakoutStrategy(
            pivot_left=1,
            pivot_right=1,
            breakout_confirmation=1,
        )
        signals = []
        for i in range(len(candles)):
            signal = await strategy.get_signal("TEST", candles[: i + 1])
            signals.append(signal)
        # Last signal should be "short"
        assert signals[-1] == "short", f"Expected short, got {signals[-1]}"

    @pytest.mark.asyncio
    async def test_no_false_breakout(self):
        """
        Price touches but does not close beyond the trendline.
        """
        # Prices: 100, 99, 98, 97, 96, 95 (descending)
        # Then wick above but close below: high=98, close=96
        prices = [100, 99, 98, 97, 96, 95]
        highs = [100, 99, 98, 97, 96, 98]  # last candle wick above
        candles = _make_candles(prices, high_prices=highs)
        strategy = TrendlineBreakoutStrategy(
            pivot_left=1,
            pivot_right=1,
            breakout_confirmation=1,
        )
        signals = []
        for i in range(len(candles)):
            signal = await strategy.get_signal("TEST", candles[: i + 1])
            signals.append(signal)
        # No breakout should be detected (close below)
        assert signals[-1] == "hold", f"Expected hold, got {signals[-1]}"

    @pytest.mark.asyncio
    async def test_stop_loss(self):
        """
        After entering long, price moves against the position
        and triggers stop loss.
        """
        # Prices: 100, 99, 98, 97, 96, 95 (descending)
        # Breakout: 97, 100 -> long entry at 100
        # Then drop: 98, 96 (stop loss at 2% -> 98)
        prices = [100, 99, 98, 97, 96, 95, 97, 100, 98, 96]
        candles = _make_candles(prices)
        strategy = TrendlineBreakoutStrategy(
            pivot_left=1,
            pivot_right=1,
            breakout_confirmation=1,
            stop_loss_pct=0.02,
        )
        signals = []
        for i in range(len(candles)):
            signal = await strategy.get_signal("TEST", candles[: i + 1])
            signals.append(signal)
        # After entry at index 7 (close=100), stop loss at 98 should trigger close
        # Index 8 close=98 -> change = (98-100)/100 = -0.02 -> stop loss
        assert signals[8] == "close", f"Expected close at index 8, got {signals[8]}"

    @pytest.mark.asyncio
    async def test_take_profit(self):
        """
        After entering long, price moves in favour and triggers take profit.
        """
        # Prices: 100, 99, 98, 97, 96, 95 (descending)
        # Breakout: 97, 100 -> long entry at 100
        # Then rise: 103, 106 (take profit at 4% -> 104)
        prices = [100, 99, 98, 97, 96, 95, 97, 100, 103, 106]
        candles = _make_candles(prices)
        strategy = TrendlineBreakoutStrategy(
            pivot_left=1,
            pivot_right=1,
            breakout_confirmation=1,
            take_profit_pct=0.04,
        )
        signals = []
        for i in range(len(candles)):
            signal = await strategy.get_signal("TEST", candles[: i + 1])
            signals.append(signal)
        # After entry at index 7 (close=100), take profit at 104 should trigger close
        # Index 9 close=106 -> change = (106-100)/100 = 0.06 >= 0.04 -> take profit
        assert signals[9] == "close", f"Expected close at index 9, got {signals[9]}"

    @pytest.mark.asyncio
    async def test_deterministic_replay(self):
        """Running the strategy multiple times yields identical signals."""
        prices = [100, 99, 98, 97, 96, 95, 97, 100, 98, 96]
        candles = _make_candles(prices)
        strategy1 = TrendlineBreakoutStrategy(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
        )
        strategy2 = TrendlineBreakoutStrategy(
            pivot_left=1, pivot_right=1, breakout_confirmation=1,
        )
        signals1 = []
        signals2 = []
        for i in range(len(candles)):
            signals1.append(await strategy1.get_signal("TEST", candles[: i + 1]))
            signals2.append(await strategy2.get_signal("TEST", candles[: i + 1]))
        assert signals1 == signals2

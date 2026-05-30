"""
Pine Script-style dual-channel engine.

Mirrors ``pinescript-HH-HL.md`` with guardrails against overtrading:
- Breakout arms a time-limited retest window (not indefinite)
- Opposite breakout cancels the pending retest
- Retest cannot fire on the same bar as breakout
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from market_data.models.candle import Candle
from market_structure.pivots import detect_swing_highs, detect_swing_lows
from market_structure.swing_structure import SwingStructureTracker, TrendStructure
from market_structure.trendline import Trendline

logger = logging.getLogger(__name__)


@dataclass
class ChannelUpdateResult:
    """Signals emitted on the latest candle."""

    bull_breakout: bool = False
    bear_breakdown: bool = False
    bull_retest: bool = False
    bear_retest: bool = False
    upper_price: Optional[float] = None
    lower_price: Optional[float] = None
    prev_upper_price: Optional[float] = None
    prev_lower_price: Optional[float] = None
    high_volume: bool = False
    volume_ratio: float = 0.0
    breakout_volume_ratio: float = 0.0
    retest_bars_elapsed: int = 0
    trend_structure: TrendStructure = TrendStructure.NEUTRAL


@dataclass
class _SwingStore:
    price1: Optional[float] = None
    price2: Optional[float] = None
    bar1: Optional[int] = None
    bar2: Optional[int] = None

    def push(self, price: float, bar: int) -> None:
        self.price2 = self.price1
        self.bar2 = self.bar1
        self.price1 = price
        self.bar1 = bar


class PineChannelEngine:
    """
    Incremental channel engine aligned with TradingView HH-HL channel script.
    """

    def __init__(
        self,
        pivot_len: int = 5,
        line_extension_bars: int = 10,
        vol_sma_period: int = 20,
        vol_multiplier: float = 1.5,
        structure_tolerance_bps: float = 0.0,
        retest_max_bars: int = 24,
        retest_min_bars_after_breakout: int = 1,
    ) -> None:
        self.pivot_len = pivot_len
        self.line_extension_bars = line_extension_bars
        self.vol_sma_period = vol_sma_period
        self.vol_multiplier = vol_multiplier
        self.retest_max_bars = retest_max_bars
        self.retest_min_bars_after_breakout = retest_min_bars_after_breakout

        self._highs = _SwingStore()
        self._lows = _SwingStore()
        self._structure = SwingStructureTracker(tolerance_bps=structure_tolerance_bps)

        self.wait_bull_retest = False
        self.wait_bear_retest = False
        self._bull_breakout_bar: Optional[int] = None
        self._bear_breakdown_bar: Optional[int] = None

        self._prev_upper: Optional[float] = None
        self._prev_lower: Optional[float] = None
        self._candle_count = 0
        self._last_bull_breakout_vol_ratio: float = 0.0
        self._last_bear_breakout_vol_ratio: float = 0.0

    @property
    def trend_structure(self) -> TrendStructure:
        return self._structure.trend

    @property
    def structure_tracker(self) -> SwingStructureTracker:
        return self._structure

    def clear_pending_entries(self) -> None:
        """Drop armed retest states (e.g. while in a position or cooldown)."""
        self._clear_bull_wait()
        self._clear_bear_wait()

    def update(self, candles: List[Candle]) -> ChannelUpdateResult:
        """Process candles up to and including the latest bar."""
        if not candles:
            return ChannelUpdateResult()

        idx = len(candles) - 1
        candle = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else None

        if idx + 1 > self._candle_count:
            self._ingest_new_pivots(candles, idx)
            self._candle_count = idx + 1

        self._expire_stale_waits(idx)

        upper = self._channel_price(self._highs, idx)
        lower = self._channel_price(self._lows, idx)
        prev_upper = self._prev_upper
        prev_lower = self._prev_lower

        high_volume = self._volume_confirmed(candles)
        vol_ratio = self._volume_ratio(candles)
        result = ChannelUpdateResult(
            upper_price=upper,
            lower_price=lower,
            prev_upper_price=prev_upper,
            prev_lower_price=prev_lower,
            high_volume=high_volume,
            volume_ratio=vol_ratio,
            trend_structure=self._structure.trend,
        )

        if upper is not None and prev is not None and prev_upper is not None:
            bull_breakout = (
                candle.close > upper
                and prev.close <= prev_upper
                and high_volume
            )
            if bull_breakout:
                self._clear_bear_wait()
                self.wait_bull_retest = True
                self._bull_breakout_bar = idx
                self._last_bull_breakout_vol_ratio = vol_ratio
                result.bull_breakout = True
                logger.info(
                    "[CHANNEL] Bull breakout close=%.2f upper=%.2f vol_ok=True",
                    candle.close, upper,
                )

        if lower is not None and prev is not None and prev_lower is not None:
            bear_breakdown = (
                candle.close < lower
                and prev.close >= prev_lower
                and high_volume
            )
            if bear_breakdown:
                self._clear_bull_wait()
                self.wait_bear_retest = True
                self._bear_breakdown_bar = idx
                self._last_bear_breakout_vol_ratio = vol_ratio
                result.bear_breakdown = True
                logger.info(
                    "[CHANNEL] Bear breakdown close=%.2f lower=%.2f vol_ok=True",
                    candle.close, lower,
                )

        if self._bull_wait_active(idx) and upper is not None:
            bull_retest = (
                candle.low <= upper
                and candle.close > upper
                and candle.close > candle.open
            )
            if bull_retest:
                elapsed = (
                    idx - self._bull_breakout_bar if self._bull_breakout_bar is not None else 0
                )
                self._clear_bull_wait()
                result.bull_retest = True
                result.retest_bars_elapsed = elapsed
                result.breakout_volume_ratio = self._last_bull_breakout_vol_ratio
                result.volume_ratio = max(vol_ratio, self._last_bull_breakout_vol_ratio)
                result.high_volume = True
                logger.info(
                    "[CHANNEL] Bull retest entry close=%.2f upper=%.2f",
                    candle.close, upper,
                )

        if self._bear_wait_active(idx) and lower is not None:
            bear_retest = (
                candle.high >= lower
                and candle.close < lower
                and candle.close < candle.open
            )
            if bear_retest:
                elapsed = (
                    idx - self._bear_breakdown_bar if self._bear_breakdown_bar is not None else 0
                )
                self._clear_bear_wait()
                result.bear_retest = True
                result.retest_bars_elapsed = elapsed
                result.breakout_volume_ratio = self._last_bear_breakout_vol_ratio
                result.volume_ratio = max(vol_ratio, self._last_bear_breakout_vol_ratio)
                result.high_volume = True
                logger.info(
                    "[CHANNEL] Bear retest entry close=%.2f lower=%.2f",
                    candle.close, lower,
                )

        self._prev_upper = upper
        self._prev_lower = lower
        return result

    def _bull_wait_active(self, idx: int) -> bool:
        if not self.wait_bull_retest or self._bull_breakout_bar is None:
            return False
        elapsed = idx - self._bull_breakout_bar
        return elapsed >= self.retest_min_bars_after_breakout

    def _bear_wait_active(self, idx: int) -> bool:
        if not self.wait_bear_retest or self._bear_breakdown_bar is None:
            return False
        elapsed = idx - self._bear_breakdown_bar
        return elapsed >= self.retest_min_bars_after_breakout

    def _expire_stale_waits(self, idx: int) -> None:
        if self.wait_bull_retest and self._bull_breakout_bar is not None:
            if idx - self._bull_breakout_bar > self.retest_max_bars:
                logger.debug("[CHANNEL] Bull retest window expired")
                self._clear_bull_wait()
        if self.wait_bear_retest and self._bear_breakdown_bar is not None:
            if idx - self._bear_breakdown_bar > self.retest_max_bars:
                logger.debug("[CHANNEL] Bear retest window expired")
                self._clear_bear_wait()

    def _clear_bull_wait(self) -> None:
        self.wait_bull_retest = False
        self._bull_breakout_bar = None

    def _clear_bear_wait(self) -> None:
        self.wait_bear_retest = False
        self._bear_breakdown_bar = None

    def _ingest_new_pivots(self, candles: List[Candle], idx: int) -> None:
        pivot_len = self.pivot_len
        if idx < 2 * pivot_len:
            return

        start = idx - 2 * pivot_len
        window = candles[start : idx + 1]
        if len(window) < 2 * pivot_len + 1:
            return

        pivot_bar = idx - pivot_len
        local_pivot = pivot_len

        highs = detect_swing_highs(window, pivot_len, pivot_len)
        if local_pivot in highs:
            price = candles[pivot_bar].high
            self._highs.push(price, pivot_bar)
            self._structure.on_swing_high(pivot_bar, price, candles[pivot_bar].timestamp)

        lows = detect_swing_lows(window, pivot_len, pivot_len)
        if local_pivot in lows:
            price = candles[pivot_bar].low
            self._lows.push(price, pivot_bar)
            self._structure.on_swing_low(pivot_bar, price, candles[pivot_bar].timestamp)

    def _channel_price(self, store: _SwingStore, bar_index: int) -> Optional[float]:
        if store.price1 is None or store.price2 is None:
            return None
        if store.bar1 is None or store.bar2 is None:
            return None

        x_end = store.bar1 + self.line_extension_bars
        line = Trendline(
            is_support=store is self._lows,
            x1=store.bar2,
            y1=store.price2,
            x2=x_end,
            y2=store.price1,
        )
        eval_bar = min(bar_index, x_end)
        return line.price_at(eval_bar)

    def _volume_ratio(self, candles: List[Candle]) -> float:
        period = self.vol_sma_period
        if len(candles) < period:
            return 0.0
        recent = candles[-period:]
        avg_vol = sum(c.volume for c in recent) / period
        if avg_vol <= 0:
            return 0.0
        return candles[-1].volume / avg_vol

    def _volume_confirmed(self, candles: List[Candle]) -> bool:
        return self._volume_ratio(candles) > self.vol_multiplier

"""
Trendline breakout strategy.

Consumes structural events (pivots, trendlines, breakouts) from the
market structure engine and generates LONG / SHORT / CLOSE signals.

Rules:
- LONG: descending resistance trendline + confirmed breakout above
- SHORT: ascending support trendline + confirmed breakdown below
- EXIT: opposite breakout, stop loss, take profit, or max holding candles

Position management:
- one position at a time (no pyramiding, no hedging)
- explicit FLAT / LONG / SHORT lifecycle

Risk controls:
- cooldown after loss
- trendline expiry (max candles since trendline built)
- pivot confirmation delay
- max holding candles
"""

import logging
from typing import Any, List, Optional

from strategy.base import BaseStrategy
from signals.structural_events import BreakoutEvent, TrendlineEvent, PivotEvent
from market_structure.pivots import detect_pivots
from market_structure.trendline import build_trendlines, Trendline
from market_structure.breakout import BreakoutDetector

logger = logging.getLogger(__name__)


class TrendlineBreakoutStrategy(BaseStrategy):
    name = "trendline_breakout"
    description = (
        "Trendline breakout strategy: enters long on resistance breakout, "
        "short on support breakdown.  Uses confirmed pivots and close‑only breakouts."
    )

    def __init__(
        self,
        config: Any = None,
        symbols: List[str] = None,
        enabled: bool = True,
        # Pivot parameters
        pivot_left: int = 2,
        pivot_right: int = 2,
        # Breakout parameters
        breakout_confirmation: int = 1,
        breakout_require_retest: bool = False,
        # Risk controls
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.04,
        max_holding_candles: int = 48,
        trendline_expiry_candles: int = 100,
        cooldown_after_loss_candles: int = 5,
        **kwargs,
    ):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.breakout_confirmation = breakout_confirmation
        self.breakout_require_retest = breakout_require_retest
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_holding_candles = max_holding_candles
        self.trendline_expiry_candles = trendline_expiry_candles
        self.cooldown_after_loss_candles = cooldown_after_loss_candles

        # Internal state
        self._position: Optional[str] = None  # "long" or "short"
        self._entry_candle: int = -1
        self._entry_price: float = 0.0
        self._last_trendline_built_at: int = -1
        self._last_loss_candle: int = -self.cooldown_after_loss_candles - 1
        self._last_signal: str = "hold"

        # Breakout detectors (one per trendline type)
        self._resistance_detector = BreakoutDetector(
            confirmation_candles=self.breakout_confirmation,
            require_retest=self.breakout_require_retest,
        )
        self._support_detector = BreakoutDetector(
            confirmation_candles=self.breakout_confirmation,
            require_retest=self.breakout_require_retest,
        )

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Generate a trading signal based on market structure events.

        Returns ``'long'``, ``'short'``, ``'close'``, or ``'hold'``.
        """
        candle_index = len(candles) - 1
        current_candle = candles[-1]
        close = current_candle.close
        timestamp_ms = current_candle.timestamp

        # ── 1. Build trendlines from confirmed pivots ─────────────
        trendlines = build_trendlines(
            candles,
            left=self.pivot_left,
            right=self.pivot_right,
        )

        # Track when trendlines were last built
        if trendlines:
            self._last_trendline_built_at = candle_index

        # ── 2. Check trendline expiry ─────────────────────────────
        if (self._last_trendline_built_at >= 0 and
                candle_index - self._last_trendline_built_at > self.trendline_expiry_candles):
            # Trendline too old – reset detectors
            self._resistance_detector.reset()
            self._support_detector.reset()
            if self._position is not None:
                logger.info("Trendline expired – closing position.")
                self._position = None
                self._entry_candle = -1
                return "close"
            return "hold"

        # ── 3. Check breakouts ────────────────────────────────────
        breakout_event: Optional[BreakoutEvent] = None

        for tl in trendlines:
            if tl.is_support:
                # Support trendline – check for breakdown (below)
                direction = self._support_detector.check_breakout(
                    current_candle, tl, candle_index
                )
                if direction == "below":
                    breakout_event = BreakoutEvent(
                        direction="below",
                        candle_index=candle_index,
                        line_price=tl.price_at(candle_index),
                        close_price=close,
                        timestamp_ms=timestamp_ms,
                        confidence=self._support_detector._consecutive_break_count,
                    )
            else:
                # Resistance trendline – check for breakout (above)
                direction = self._resistance_detector.check_breakout(
                    current_candle, tl, candle_index
                )
                if direction == "above":
                    breakout_event = BreakoutEvent(
                        direction="above",
                        candle_index=candle_index,
                        line_price=tl.price_at(candle_index),
                        close_price=close,
                        timestamp_ms=timestamp_ms,
                        confidence=self._resistance_detector._consecutive_break_count,
                    )

        # ── 4. Cooldown after loss ────────────────────────────────
        if candle_index - self._last_loss_candle < self.cooldown_after_loss_candles:
            return "hold"

        # ── 5. Position management ────────────────────────────────
        signal = "hold"

        if self._position is None:
            # No position – look for entry signals
            if breakout_event is not None:
                if breakout_event.direction == "above":
                    # Resistance breakout -> LONG
                    signal = "long"
                    logger.info(
                        "Breakout above resistance at index %d (line=%.2f, close=%.2f) -> LONG",
                        candle_index, breakout_event.line_price, breakout_event.close_price,
                    )
                elif breakout_event.direction == "below":
                    # Support breakdown -> SHORT
                    signal = "short"
                    logger.info(
                        "Breakdown below support at index %d (line=%.2f, close=%.2f) -> SHORT",
                        candle_index, breakout_event.line_price, breakout_event.close_price,
                    )
        else:
            # Position open – check exit conditions
            exit_reason: Optional[str] = None

            # Opposite breakout
            if breakout_event is not None:
                if self._position == "long" and breakout_event.direction == "below":
                    exit_reason = "opposite_breakout"
                elif self._position == "short" and breakout_event.direction == "above":
                    exit_reason = "opposite_breakout"

            # Stop loss
            if exit_reason is None:
                if self._position == "long":
                    change = (close - self._entry_price) / self._entry_price
                    if change <= -self.stop_loss_pct:
                        exit_reason = "stop_loss"
                else:
                    change = (self._entry_price - close) / self._entry_price
                    if change <= -self.stop_loss_pct:
                        exit_reason = "stop_loss"

            # Take profit
            if exit_reason is None:
                if self._position == "long":
                    change = (close - self._entry_price) / self._entry_price
                    if change >= self.take_profit_pct:
                        exit_reason = "take_profit"
                else:
                    change = (self._entry_price - close) / self._entry_price
                    if change >= self.take_profit_pct:
                        exit_reason = "take_profit"

            # Max holding candles
            if exit_reason is None:
                if candle_index - self._entry_candle >= self.max_holding_candles:
                    exit_reason = "max_holding"

            if exit_reason is not None:
                signal = "close"
                logger.info(
                    "Closing %s at index %d (close=%.2f, reason=%s)",
                    self._position.upper(), candle_index, close, exit_reason,
                )
                # Record loss for cooldown
                if exit_reason in ("stop_loss", "opposite_breakout"):
                    self._last_loss_candle = candle_index
                self._position = None
                self._entry_candle = -1

        # ── 6. Update position state on entry ─────────────────────
        if signal in ("long", "short") and self._position is None:
            self._position = signal
            self._entry_candle = candle_index
            self._entry_price = close

        self._last_signal = signal
        return signal

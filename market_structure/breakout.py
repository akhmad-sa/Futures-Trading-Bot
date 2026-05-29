"""
Breakout detection using trendlines.

Determines whether the current candle has broken through a support or
resistance trendline.  By default only **close** price breakouts are
considered; wick‑only breakouts are ignored (configurable via the
``use_wick`` parameter).

Supports optional retest confirmation, cooldown, duplicate breakout
prevention, minimum distance threshold, and body strength filtering.
"""

import logging
from typing import Dict, Optional

from market_data.models.candle import Candle
from market_structure.trendline import Trendline

logger = logging.getLogger(__name__)


class BreakoutDetector:
    """
    Detects breakouts of a given trendline.

    Parameters
    ----------
    confirmation_candles : int
        Number of consecutive closes beyond the trendline required for confirmation.
    require_retest : bool
        Whether to require a retest of the trendline after breakout.
    use_wick : bool
        If ``True``, a wick that touches/straddles the line is considered
        a breakout.  Default ``False`` (close‑only).
    cooldown_candles : int
        After a confirmed breakout, ignore further breakouts on the same
        trendline for this many candles (duplicate prevention).
    min_distance_bps : float
        Minimum distance (in basis points) between close price and line price
        required for a valid breakout.  Breakouts smaller than this are ignored.
    min_body_ratio : float
        Minimum ratio of candle body (|close‑open|) to total range (high‑low)
        for a breakout candle.  Only applied if > 0.
    """

    def __init__(
        self,
        confirmation_candles: int = 1,
        require_retest: bool = False,
        use_wick: bool = False,
        cooldown_candles: int = 0,
        min_distance_bps: float = 0.0,
        min_body_ratio: float = 0.0,
    ):
        self._confirmation = confirmation_candles
        self._require_retest = require_retest
        self._use_wick = use_wick
        self._cooldown = cooldown_candles
        self._min_distance_bps = min_distance_bps
        self._min_body_ratio = min_body_ratio
        self._consecutive_break_count = 0
        self._retest_observed = False
        self._last_breakout_direction: Optional[str] = None  # "above" or "below"
        self._last_breakout_candle: int = -1  # index of last confirmed breakout

        # ── Deduplication state ──────────────────────────────────
        # Maps id(trendline) -> True once a breakout has been emitted for that trendline.
        self._emitted_breakouts: Dict[int, bool] = {}

    # ── Public helpers for resetting emitted state ────────────────

    def reset_emitted_for_trendline(self, trendline: Trendline) -> None:
        """
        Reset the emitted flag for *trendline*.

        Call this when the trendline is invalidated, expires, or when
        the price returns inside the trendline (the detector also does
        this automatically when it detects an inside candle).
        """
        key = id(trendline)
        self._emitted_breakouts.pop(key, None)

    def reset_all_emitted(self) -> None:
        """Reset all emitted flags (e.g., when starting a new market structure)."""
        self._emitted_breakouts.clear()
        self._consecutive_break_count = 0
        self._retest_observed = False
        self._last_breakout_direction = None
        self._last_breakout_candle = -1

    # ── Core breakout logic ──────────────────────────────────────

    def check_breakout(
        self, candle: Candle, trendline: Trendline, candle_index: int
    ) -> Optional[str]:
        """
        Check if the current candle breaks through *trendline*.

        Returns ``'above'`` if price closes above resistance,
        ``'below'`` if price closes below support, or ``None`` if no
        confirmed breakout.

        When *require_retest* is True, a breakout is only confirmed after
        a subsequent candle retests the trendline (closes back to the
        line within a small tolerance).
        """
        # ── Cooldown check ────────────────────────────────────────
        if self._cooldown > 0 and self._last_breakout_candle >= 0:
            if candle_index - self._last_breakout_candle < self._cooldown:
                return None

        # ── Deduplication: already emitted for this trendline? ────
        key = id(trendline)
        if self._emitted_breakouts.get(key, False):
            return None

        line_price = trendline.price_at(candle_index)
        close = candle.close
        high = candle.high
        low = candle.low

        # ── Minimum distance filter ───────────────────────────────
        distance_bps = abs(close - line_price) / line_price * 10_000
        if distance_bps < self._min_distance_bps:
            return None

        # ── Body strength filter ─────────────────────────────────
        if self._min_body_ratio > 0:
            body = abs(close - candle.open)
            total_range = high - low
            if total_range > 0 and body / total_range < self._min_body_ratio:
                return None

        # Determine direction of break relative to trendline type
        direction: Optional[str] = None
        if trendline.is_support:
            # Support line – a break occurs when price closes below it
            if close < line_price:
                direction = "below"
            elif self._use_wick and low < line_price and close >= line_price:
                direction = "below"
        else:
            # Resistance line – a break occurs when price closes above it
            if close > line_price:
                direction = "above"
            elif self._use_wick and high > line_price and close <= line_price:
                direction = "above"

        # ── Reset emitted state when price returns inside ────────
        if direction is None:
            # Candle did not break out – check if it is inside the trendline
            if self._is_inside(candle, trendline, line_price):
                self._emitted_breakouts.pop(key, None)
            # Also reset consecutive counter and retest flag
            self._consecutive_break_count = 0
            self._retest_observed = False
            return None

        # Update consecutive counter
        if direction == self._last_breakout_direction:
            self._consecutive_break_count += 1
        else:
            self._consecutive_break_count = 1
            self._last_breakout_direction = direction

        # Check confirmation count
        if self._consecutive_break_count >= self._confirmation:
            if self._require_retest:
                if self._retest_observed:
                    self._retest_observed = False
                    # Confirm breakout
                    self._last_breakout_candle = candle_index
                    self._emitted_breakouts[key] = True
                    trendline.breakout_index = candle_index
                    logger.info(
                        "Breakout confirmed with retest: %s at index %d, time=%d",
                        direction, candle_index, candle.timestamp,
                    )
                    return direction
                # Check if this candle itself is a retest
                tolerance = line_price * 0.001
                if abs(close - line_price) <= tolerance:
                    self._retest_observed = True
                return None
            else:
                # Direct confirmation
                self._last_breakout_candle = candle_index
                self._emitted_breakouts[key] = True
                trendline.breakout_index = candle_index
                logger.info(
                    "Breakout detected: %s at index %d (trendline=%.2f, close=%.2f, time=%d)",
                    direction, candle_index, line_price, close, candle.timestamp,
                )
                return direction

        return None

    # ── Internal helpers ─────────────────────────────────────────

    def _is_inside(
        self, candle: Candle, trendline: Trendline, line_price: float
    ) -> bool:
        """
        Return ``True`` if the candle is on the *safe* side of the
        trendline (i.e., not beyond it).  For a support line this means
        the close is **above** the line; for a resistance line it means
        the close is **below** the line.
        """
        if trendline.is_support:
            # Support: inside means close >= line_price
            return candle.close >= line_price
        else:
            # Resistance: inside means close <= line_price
            return candle.close <= line_price

    def reset(self) -> None:
        """Reset internal state (for new trendline or fresh start)."""
        self._consecutive_break_count = 0
        self._retest_observed = False
        self._last_breakout_direction = None
        self._last_breakout_candle = -1
        self._emitted_breakouts.clear()

    def consume_trendline(self, trendline: Trendline) -> None:
        """Manually mark a trendline as consumed (e.g., after opposite breakout)."""
        # This method is kept for backward compatibility; it now resets
        # the emitted flag so that a future breakout on the same trendline
        # can be detected again.
        self.reset_emitted_for_trendline(trendline)

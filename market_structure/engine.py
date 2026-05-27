"""
Persistent market structure engine.

Maintains pivot history, active trendlines, and per‑trendline breakout
detectors incrementally across candles.
"""

import logging
from typing import List, Optional, Tuple

from market_data.models.candle import Candle
from market_structure.pivots import (
    detect_swing_highs,
    detect_swing_lows,
    detect_pivots,
)
from market_structure.trendline import build_trendlines, Trendline
from market_structure.breakout import BreakoutDetector
from market_structure.active_trendline import ActiveTrendline
from signals.structural_events import (
    StructuralEvent,
    PivotEvent,
    TrendlineCreatedEvent,
    TrendlineInvalidatedEvent,
    BreakoutEvent,
)

logger = logging.getLogger(__name__)


class MarketStructureEngine:
    """
    Persistent market structure engine.

    Maintains:
    - pivot history (self.pivots_highs, self.pivots_lows)
    - active trendlines with per‑line breakout detectors
    - structural event generation

    Call update(candle) every candle to evolve the structure.
    """

    def __init__(
        self,
        pivot_left: int = 2,
        pivot_right: int = 2,
        min_pivot_spacing: int = 3,
        min_price_delta_pct: float = 0.005,
        breakout_confirmation: int = 1,
        breakout_require_retest: bool = False,
        trendline_max_age: int = 100,
        min_breakout_bps: float = 0.0,
        volatility_filter_enabled: bool = False,
        min_atr_percent: float = 0.0,
        body_strength_filter_enabled: bool = False,
        min_body_ratio: float = 0.0,
    ) -> None:
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.min_pivot_spacing = min_pivot_spacing
        self.min_price_delta_pct = min_price_delta_pct
        self.breakout_confirmation = breakout_confirmation
        self.breakout_require_retest = breakout_require_retest
        self.trendline_max_age = trendline_max_age
        self.min_breakout_bps = min_breakout_bps
        self.volatility_filter_enabled = volatility_filter_enabled
        self.min_atr_percent = min_atr_percent
        self.body_strength_filter_enabled = body_strength_filter_enabled
        self.min_body_ratio = min_body_ratio

        # ── Persistent state ──────────────────────────────────────
        self.candle_count: int = 0
        self.pivots_highs: List[int] = []
        self.pivots_lows: List[int] = []
        self.active_trendlines: List[ActiveTrendline] = []
        self._trendline_counter: int = 0

        # Store last few candles for ATR calculation if needed
        self._candle_buffer: List[Candle] = []

    def update(self, candle: Candle) -> List[StructuralEvent]:
        """
        Process one candle and return any structural events.

        Must be called in chronological order.
        """
        events: List[StructuralEvent] = []
        idx = self.candle_count
        self._candle_buffer.append(candle)
        self.candle_count += 1

        # ── 1. Detect new pivots ─────────────────────────────────
        new_highs = self._detect_new_pivots(candle, idx)
        new_lows = self._detect_new_pivots(candle, idx, detect_lows=True)

        for hi in new_highs:
            self.pivots_highs.append(hi)
            events.append(
                PivotEvent(
                    pivot_type="high",
                    candle_index=hi,
                    price=candle.high if hi == idx else candle.high,
                    timestamp_ms=candle.timestamp,
                )
            )
        for li in new_lows:
            self.pivots_lows.append(li)
            events.append(
                PivotEvent(
                    pivot_type="low",
                    candle_index=li,
                    price=candle.low if li == idx else candle.low,
                    timestamp_ms=candle.timestamp,
                )
            )

        # ── 2. Build new trendlines if enough pivots exist ───────
        new_lines = self._build_new_trendlines()
        for tl_data in new_lines:
            tl_id = self._next_trendline_id(tl_data["is_support"])
            atl = ActiveTrendline(
                id=tl_id,
                line=tl_data["line"],
                created_index=idx,
                last_touch_index=idx,
                breakout_detector=BreakoutDetector(
                    confirmation_candles=self.breakout_confirmation,
                    require_retest=self.breakout_require_retest,
                ),
            )
            self.active_trendlines.append(atl)
            slope = self._compute_slope(tl_data["line"])
            events.append(
                TrendlineCreatedEvent(
                    trendline_id=tl_id,
                    is_support=tl_data["is_support"],
                    x1=tl_data["line"].x1,
                    y1=tl_data["line"].y1,
                    x2=tl_data["line"].x2,
                    y2=tl_data["line"].y2,
                    slope=slope,
                    timestamp_ms=candle.timestamp,
                )
            )
            logger.info(
                "[TRENDLINE] Created %s id=%s slope=%.4f",
                "support" if tl_data["is_support"] else "resistance",
                tl_id, slope,
            )

        # ── 3. Expire old trendlines ─────────────────────────────
        for atl in self.active_trendlines[:]:
            if atl.expired or atl.is_broken:
                continue
            if idx - atl.created_index > self.trendline_max_age:
                atl.expired = True
                atl.is_valid = False
                events.append(
                    TrendlineInvalidatedEvent(
                        trendline_id=atl.id,
                        reason="expired",
                        candle_index=idx,
                        timestamp_ms=candle.timestamp,
                    )
                )
                logger.info(
                    "[TRENDLINE] Expired id=%s (age=%d candles)",
                    atl.id, idx - atl.created_index,
                )

        # ── 4. Check breakouts on valid trendlines ──────────────
        for atl in self.active_trendlines:
            if not atl.is_valid or atl.expired or atl.is_broken:
                continue

            line_price = atl.line.price_at(idx)
            detector = atl.breakout_detector
            if detector is None:
                continue
            # Apply distance filter before calling detector
            distance_bps = abs(candle.close - line_price) / line_price * 10_000
            if distance_bps < self.min_breakout_bps:
                continue

            # Apply volatility filter (simple: range over last N)
            if self.volatility_filter_enabled and self.min_atr_percent > 0:
                atr = self._estimate_atr(14)
                if atr == 0 or atr / line_price * 100 < self.min_atr_percent:
                    continue

            # Apply body strength filter
            if self.body_strength_filter_enabled and self.min_body_ratio > 0:
                body = abs(candle.close - candle.open)
                range_total = candle.high - candle.low
                if range_total > 0 and body / range_total < self.min_body_ratio:
                    continue

            direction = detector.check_breakout(candle, atl.line, idx)

            if direction is not None:
                atl.is_broken = True
                atl.is_valid = False
                atl.breakout_count += 1
                events.append(
                    BreakoutEvent(
                        trendline_id=atl.id,
                        direction=direction,
                        candle_index=idx,
                        line_price=line_price,
                        close_price=candle.close,
                        distance_bps=distance_bps,
                        timestamp_ms=candle.timestamp,
                        confidence=detector._consecutive_break_count,
                    )
                )
                side_label = "ABOVE" if direction == "above" else "BELOW"
                logger.info(
                    "[BREAKOUT] %s line=%s close=%.2f dist=%.1f bps",
                    side_label, atl.id, candle.close, distance_bps,
                )

        # ── 5. Trim candle buffer (keep last 200) ────────────────
        if len(self._candle_buffer) > 200:
            self._candle_buffer = self._candle_buffer[-200:]

        return events

    # ── Internal helpers ──────────────────────────────────────────

    def _detect_new_pivots(
        self, candle: Candle, idx: int, detect_lows: bool = False
    ) -> List[int]:
        """
        Check whether the current candle forms a new pivot given the
        current state.  Returns a list (0 or 1 element) of the pivot index.
        """
        # We need at least (left + right) past candles to confirm
        if idx < self.pivot_left + self.pivot_right:
            return []

        # Build a short sub‑list of the latest needed candles
        start = idx - self.pivot_left - self.pivot_right
        sub = self._candle_buffer[start: idx + 1]
        if len(sub) < self.pivot_left + self.pivot_right + 1:
            return []

        if detect_lows:
            lows = detect_swing_lows(sub, self.pivot_left, self.pivot_right)
        else:
            highs = detect_swing_highs(sub, self.pivot_left, self.pivot_right)

        indices = lows if detect_lows else highs
        # Adjust indices to global candle index
        global_indices = [start + i for i in indices]
        # Only return the newest pivot (should be idx if it is a pivot)
        result = [g for g in global_indices if g >= idx - self.pivot_right]
        return result

    def _build_new_trendlines(self) -> List[dict]:
        """
        Build new trendlines if new pivot pairs exist that are not yet
        represented by an active trendline.
        """
        if len(self.pivots_highs) < 2 and len(self.pivots_lows) < 2:
            return []

        new_lines: List[dict] = []

        # Check for new resistance line
        if len(self.pivots_highs) >= 2:
            h1 = self.pivots_highs[-2]
            h2 = self.pivots_highs[-1]
            if abs(h2 - h1) >= self.min_pivot_spacing:
                price1 = self._candle_buffer[h1].high if h1 < len(self._candle_buffer) else 0
                price2 = self._candle_buffer[h2].high if h2 < len(self._candle_buffer) else 0
                if price1 > 0 and price2 > 0:
                    delta = abs(price2 - price1) / price1
                    if delta >= self.min_price_delta_pct:
                        # Check if we already have a resistance line using these pivots
                        if not self._has_line_for_pivots(h1, h2, is_support=False):
                            tl = Trendline(
                                is_support=False, x1=h1, y1=price1,
                                x2=h2, y2=price2,
                                created_at_index=h2, last_touch_index=h2, active=True,
                            )
                            new_lines.append({"line": tl, "is_support": False})

        # Check for new support line
        if len(self.pivots_lows) >= 2:
            l1 = self.pivots_lows[-2]
            l2 = self.pivots_lows[-1]
            if abs(l2 - l1) >= self.min_pivot_spacing:
                price1 = self._candle_buffer[l1].low if l1 < len(self._candle_buffer) else 0
                price2 = self._candle_buffer[l2].low if l2 < len(self._candle_buffer) else 0
                if price1 > 0 and price2 > 0:
                    delta = abs(price2 - price1) / price1
                    if delta >= self.min_price_delta_pct:
                        if not self._has_line_for_pivots(l1, l2, is_support=True):
                            tl = Trendline(
                                is_support=True, x1=l1, y1=price1,
                                x2=l2, y2=price2,
                                created_at_index=l2, last_touch_index=l2, active=True,
                            )
                            new_lines.append({"line": tl, "is_support": True})

        return new_lines

    def _has_line_for_pivots(self, x1: int, x2: int, is_support: bool) -> bool:
        """Check if an active (non‑broken, non‑expired) line already uses these pivots."""
        for atl in self.active_trendlines:
            if not atl.is_valid or atl.expired or atl.is_broken:
                continue
            if atl.line.is_support != is_support:
                continue
            if atl.line.x1 == x1 and atl.line.x2 == x2:
                return True
        return False

    def _next_trendline_id(self, is_support: bool) -> str:
        self._trendline_counter += 1
        prefix = "S" if is_support else "R"
        return f"{prefix}{self._trendline_counter}"

    def _compute_slope(self, line: Trendline) -> float:
        if line.x2 == line.x1:
            return 0.0
        return (line.y2 - line.y1) / (line.x2 - line.x1)

    def _estimate_atr(self, period: int) -> float:
        """Simple ATR over the last *period* candles in the buffer."""
        buf = self._candle_buffer
        if len(buf) < period + 1:
            return 0.0
        tr_sum = 0.0
        for i in range(len(buf) - period, len(buf)):
            c = buf[i]
            prev = buf[i - 1] if i > 0 else buf[i]
            tr = max(
                c.high - c.low,
                abs(c.high - prev.close),
                abs(c.low - prev.close),
            )
            tr_sum += tr
        return tr_sum / period

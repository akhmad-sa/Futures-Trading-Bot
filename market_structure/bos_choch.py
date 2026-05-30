"""
BOS (Break of Structure) and CHoCH (Change of Character) detection.

SMC-style structure breaks on confirmed swing levels:

- **BOS bullish**: close breaks above the last swing high while bias is bullish/neutral
- **BOS bearish**: close breaks below the last swing low while bias is bearish/neutral
- **CHoCH bullish**: close breaks above the last swing high while bias is bearish
- **CHoCH bearish**: close breaks below the last swing low while bias is bullish

Bias updates immediately on each break event. HH/HL swing labels remain available
separately via :class:`SwingStructureTracker`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from market_structure.swing_structure import TrendStructure

logger = logging.getLogger(__name__)


class StructureBreakKind(str, Enum):
    BOS_BULLISH = "bos_bullish"
    BOS_BEARISH = "bos_bearish"
    CHOCH_BULLISH = "choch_bullish"
    CHOCH_BEARISH = "choch_bearish"


@dataclass(frozen=True)
class SwingLevel:
    candle_index: int
    price: float
    timestamp_ms: int


@dataclass(frozen=True)
class StructureBreakEvent:
    kind: StructureBreakKind
    candle_index: int
    close_price: float
    broken_level: float
    broken_swing_index: int
    broken_swing_type: str  # "high" or "low"
    timestamp_ms: int
    bias_after: TrendStructure


@dataclass
class StructureState:
    """Snapshot consumed by strategies and MTF feeds."""

    trend: TrendStructure
    bias: TrendStructure
    last_break: Optional[StructureBreakEvent] = None

    @property
    def effective_trend(self) -> TrendStructure:
        """BOS/CHoCH bias when set, otherwise HH/HL trend."""
        if self.bias != TrendStructure.NEUTRAL:
            return self.bias
        return self.trend

    def allows_long(self) -> bool:
        return self.effective_trend == TrendStructure.UPTREND

    def allows_short(self) -> bool:
        return self.effective_trend == TrendStructure.DOWNTREND

    def blocks_long_entry(self) -> bool:
        """True when the latest structure break is bearish CHoCH (against longs)."""
        if self.last_break is None:
            return False
        return self.last_break.kind == StructureBreakKind.CHOCH_BEARISH

    def blocks_short_entry(self) -> bool:
        """True when the latest structure break is bullish CHoCH (against shorts)."""
        if self.last_break is None:
            return False
        return self.last_break.kind == StructureBreakKind.CHOCH_BULLISH

    def choch_exits_long(self, entry_timestamp_ms: int) -> bool:
        """True when bearish CHoCH occurred after *entry_timestamp_ms*."""
        brk = self.last_break
        if brk is None or brk.kind != StructureBreakKind.CHOCH_BEARISH:
            return False
        return brk.timestamp_ms > entry_timestamp_ms

    def choch_exits_short(self, entry_timestamp_ms: int) -> bool:
        """True when bullish CHoCH occurred after *entry_timestamp_ms*."""
        brk = self.last_break
        if brk is None or brk.kind != StructureBreakKind.CHOCH_BULLISH:
            return False
        return brk.timestamp_ms > entry_timestamp_ms


def classify_break(
    direction: str,
    bias: TrendStructure,
) -> StructureBreakKind:
    """Map a bullish/bearish break to BOS or CHoCH given current bias."""
    if direction == "bullish":
        if bias == TrendStructure.DOWNTREND:
            return StructureBreakKind.CHOCH_BULLISH
        return StructureBreakKind.BOS_BULLISH
    if bias == TrendStructure.UPTREND:
        return StructureBreakKind.CHOCH_BEARISH
    return StructureBreakKind.BOS_BEARISH


class StructureBreakTracker:
    """
    Incrementally detects BOS/CHoCH on candle closes against swing levels.

    Each swing high/low can produce at most one break event (no duplicates).
    """

    def __init__(
        self,
        *,
        confirm_with_close: bool = True,
        break_tolerance_bps: float = 0.0,
    ) -> None:
        self.confirm_with_close = confirm_with_close
        self.break_tolerance_bps = break_tolerance_bps
        self.bias: TrendStructure = TrendStructure.NEUTRAL
        self.last_swing_high: Optional[SwingLevel] = None
        self.last_swing_low: Optional[SwingLevel] = None
        self.last_break: Optional[StructureBreakEvent] = None
        self.events: List[StructureBreakEvent] = []
        self._broken_high_indices: set[int] = set()
        self._broken_low_indices: set[int] = set()

    def on_swing_high(
        self, candle_index: int, price: float, timestamp_ms: int
    ) -> None:
        self.last_swing_high = SwingLevel(candle_index, price, timestamp_ms)

    def on_swing_low(
        self, candle_index: int, price: float, timestamp_ms: int
    ) -> None:
        self.last_swing_low = SwingLevel(candle_index, price, timestamp_ms)

    def on_candle_close(
        self,
        candle_index: int,
        close: float,
        high: float,
        low: float,
        timestamp_ms: int,
    ) -> List[StructureBreakEvent]:
        """Check the latest bar for structure breaks. Returns new events only."""
        new_events: List[StructureBreakEvent] = []
        check_high = close if self.confirm_with_close else high
        check_low = close if self.confirm_with_close else low

        bullish = self._check_bullish_break(
            candle_index, check_high, timestamp_ms
        )
        if bullish:
            new_events.append(bullish)

        bearish = self._check_bearish_break(
            candle_index, check_low, timestamp_ms
        )
        if bearish:
            new_events.append(bearish)

        for event in new_events:
            self.events.append(event)
            self.last_break = event
            self.bias = event.bias_after
            logger.info(
                "[STRUCTURE] %s @ idx=%d close=%.2f level=%.2f bias=%s",
                event.kind.value,
                candle_index,
                event.close_price,
                event.broken_level,
                event.bias_after.value,
            )
        return new_events

    def _above_level(self, price: float, level: float) -> bool:
        threshold = level * (1 + self.break_tolerance_bps / 10_000)
        return price > threshold

    def _below_level(self, price: float, level: float) -> bool:
        threshold = level * (1 - self.break_tolerance_bps / 10_000)
        return price < threshold

    def _check_bullish_break(
        self,
        candle_index: int,
        price: float,
        timestamp_ms: int,
    ) -> Optional[StructureBreakEvent]:
        swing = self.last_swing_high
        if swing is None:
            return None
        if swing.candle_index in self._broken_high_indices:
            return None
        if not self._above_level(price, swing.price):
            return None

        kind = classify_break("bullish", self.bias)
        self._broken_high_indices.add(swing.candle_index)
        return StructureBreakEvent(
            kind=kind,
            candle_index=candle_index,
            close_price=price,
            broken_level=swing.price,
            broken_swing_index=swing.candle_index,
            broken_swing_type="high",
            timestamp_ms=timestamp_ms,
            bias_after=TrendStructure.UPTREND,
        )

    def _check_bearish_break(
        self,
        candle_index: int,
        price: float,
        timestamp_ms: int,
    ) -> Optional[StructureBreakEvent]:
        swing = self.last_swing_low
        if swing is None:
            return None
        if swing.candle_index in self._broken_low_indices:
            return None
        if not self._below_level(price, swing.price):
            return None

        kind = classify_break("bearish", self.bias)
        self._broken_low_indices.add(swing.candle_index)
        return StructureBreakEvent(
            kind=kind,
            candle_index=candle_index,
            close_price=price,
            broken_level=swing.price,
            broken_swing_index=swing.candle_index,
            broken_swing_type="low",
            timestamp_ms=timestamp_ms,
            bias_after=TrendStructure.DOWNTREND,
        )

    def allows_long(self) -> bool:
        return self.bias == TrendStructure.UPTREND

    def allows_short(self) -> bool:
        return self.bias == TrendStructure.DOWNTREND

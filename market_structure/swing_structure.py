"""
HH / HL / LH / LL swing classification and trend structure detection.

Uptrend  : most recent swing high is HH **and** most recent swing low is HL.
Downtrend: most recent swing high is LH **and** most recent swing low is LL.
Neutral  : mixed labels, equal swings, or insufficient pivots.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class SwingLabel(str, Enum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    EH = "EH"  # equal high (within tolerance)
    EL = "EL"  # equal low (within tolerance)


class TrendStructure(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class ClassifiedSwing:
    """A confirmed pivot with its HH/HL/LH/LL label."""

    candle_index: int
    price: float
    timestamp_ms: int
    pivot_type: str  # "high" or "low"
    label: Optional[SwingLabel]  # None for the first pivot of each type


def classify_high(
    price: float, previous_price: Optional[float], tolerance_bps: float = 0.0
) -> Optional[SwingLabel]:
    if previous_price is None:
        return None
    delta_bps = (price - previous_price) / previous_price * 10_000
    if abs(delta_bps) <= tolerance_bps:
        return SwingLabel.EH
    return SwingLabel.HH if price > previous_price else SwingLabel.LH


def classify_low(
    price: float, previous_price: Optional[float], tolerance_bps: float = 0.0
) -> Optional[SwingLabel]:
    if previous_price is None:
        return None
    delta_bps = (price - previous_price) / previous_price * 10_000
    if abs(delta_bps) <= tolerance_bps:
        return SwingLabel.EL
    return SwingLabel.HL if price > previous_price else SwingLabel.LL


def resolve_trend(
    last_high_label: Optional[SwingLabel],
    last_low_label: Optional[SwingLabel],
) -> TrendStructure:
    if last_high_label == SwingLabel.HH and last_low_label == SwingLabel.HL:
        return TrendStructure.UPTREND
    if last_high_label == SwingLabel.LH and last_low_label == SwingLabel.LL:
        return TrendStructure.DOWNTREND
    return TrendStructure.NEUTRAL


class SwingStructureTracker:
    """Incrementally classifies swing pivots and tracks trend structure."""

    def __init__(self, tolerance_bps: float = 0.0) -> None:
        self.tolerance_bps = tolerance_bps
        self.swing_highs: List[ClassifiedSwing] = []
        self.swing_lows: List[ClassifiedSwing] = []
        self.trend: TrendStructure = TrendStructure.NEUTRAL

    @property
    def last_high_label(self) -> Optional[SwingLabel]:
        if not self.swing_highs:
            return None
        return self.swing_highs[-1].label

    @property
    def last_low_label(self) -> Optional[SwingLabel]:
        if not self.swing_lows:
            return None
        return self.swing_lows[-1].label

    def allows_long(self) -> bool:
        return self.trend == TrendStructure.UPTREND

    def allows_short(self) -> bool:
        return self.trend == TrendStructure.DOWNTREND

    def on_swing_high(
        self, candle_index: int, price: float, timestamp_ms: int
    ) -> ClassifiedSwing:
        prev_price = self.swing_highs[-1].price if self.swing_highs else None
        label = classify_high(price, prev_price, self.tolerance_bps)
        swing = ClassifiedSwing(
            candle_index=candle_index,
            price=price,
            timestamp_ms=timestamp_ms,
            pivot_type="high",
            label=label,
        )
        self.swing_highs.append(swing)
        self._refresh_trend()
        if label is not None:
            logger.info(
                "[STRUCTURE] Swing high %s @ idx=%d price=%.2f trend=%s",
                label.value, candle_index, price, self.trend.value,
            )
        return swing

    def on_swing_low(
        self, candle_index: int, price: float, timestamp_ms: int
    ) -> ClassifiedSwing:
        prev_price = self.swing_lows[-1].price if self.swing_lows else None
        label = classify_low(price, prev_price, self.tolerance_bps)
        swing = ClassifiedSwing(
            candle_index=candle_index,
            price=price,
            timestamp_ms=timestamp_ms,
            pivot_type="low",
            label=label,
        )
        self.swing_lows.append(swing)
        self._refresh_trend()
        if label is not None:
            logger.info(
                "[STRUCTURE] Swing low %s @ idx=%d price=%.2f trend=%s",
                label.value, candle_index, price, self.trend.value,
            )
        return swing

    def _refresh_trend(self) -> None:
        prev = self.trend
        self.trend = resolve_trend(self.last_high_label, self.last_low_label)
        if self.trend != prev and self.last_high_label and self.last_low_label:
            logger.info(
                "[STRUCTURE] Trend changed %s -> %s (high=%s low=%s)",
                prev.value,
                self.trend.value,
                self.last_high_label.value,
                self.last_low_label.value,
            )

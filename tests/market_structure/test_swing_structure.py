"""
Tests for HH/HL/LH/LL swing structure classification.
"""

from market_structure.swing_structure import (
    SwingLabel,
    SwingStructureTracker,
    TrendStructure,
    classify_high,
    classify_low,
    resolve_trend,
)


class TestSwingClassification:
    def test_classify_high_hh_lh(self):
        assert classify_high(105.0, 100.0) == SwingLabel.HH
        assert classify_high(95.0, 100.0) == SwingLabel.LH

    def test_classify_low_hl_ll(self):
        assert classify_low(95.0, 90.0) == SwingLabel.HL
        assert classify_low(85.0, 90.0) == SwingLabel.LL

    def test_equal_within_tolerance(self):
        assert classify_high(100.0, 100.0, tolerance_bps=5.0) == SwingLabel.EH
        assert classify_low(90.0, 90.0, tolerance_bps=5.0) == SwingLabel.EL

    def test_resolve_uptrend(self):
        assert resolve_trend(SwingLabel.HH, SwingLabel.HL) == TrendStructure.UPTREND

    def test_resolve_downtrend(self):
        assert resolve_trend(SwingLabel.LH, SwingLabel.LL) == TrendStructure.DOWNTREND

    def test_resolve_neutral_mixed(self):
        assert resolve_trend(SwingLabel.HH, SwingLabel.LL) == TrendStructure.NEUTRAL
        assert resolve_trend(SwingLabel.LH, SwingLabel.HL) == TrendStructure.NEUTRAL
        assert resolve_trend(None, SwingLabel.HL) == TrendStructure.NEUTRAL


class TestSwingStructureTracker:
    def test_incremental_uptrend(self):
        tracker = SwingStructureTracker()
        tracker.on_swing_low(1, 90.0, 1000)
        tracker.on_swing_high(3, 100.0, 3000)
        tracker.on_swing_low(5, 95.0, 5000)
        assert tracker.last_low_label == SwingLabel.HL
        assert tracker.trend == TrendStructure.NEUTRAL

        tracker.on_swing_high(7, 105.0, 7000)
        assert tracker.last_high_label == SwingLabel.HH
        assert tracker.trend == TrendStructure.UPTREND
        assert tracker.allows_long()
        assert not tracker.allows_short()

    def test_incremental_downtrend(self):
        tracker = SwingStructureTracker()
        tracker.on_swing_high(1, 100.0, 1000)
        tracker.on_swing_low(3, 90.0, 3000)
        tracker.on_swing_high(5, 95.0, 5000)
        assert tracker.last_high_label == SwingLabel.LH
        assert tracker.trend == TrendStructure.NEUTRAL

        tracker.on_swing_low(7, 85.0, 7000)
        assert tracker.last_low_label == SwingLabel.LL
        assert tracker.trend == TrendStructure.DOWNTREND
        assert tracker.allows_short()
        assert not tracker.allows_long()

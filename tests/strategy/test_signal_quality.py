from market_data.models.candle import Candle
from market_structure.channel_engine import ChannelUpdateResult
from market_structure.swing_structure import TrendStructure
from strategy.signal_quality import score_retest_entry


def _candle(**kw) -> Candle:
    defaults = dict(open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0, timestamp=0)
    defaults.update(kw)
    return Candle(**defaults)


def test_high_quality_long_scores_above_70():
    ch = ChannelUpdateResult(
        bull_retest=True,
        high_volume=True,
        volume_ratio=5.0,
        retest_bars_elapsed=3,
        trend_structure=TrendStructure.UPTREND,
    )
    candle = _candle(open=100.0, close=101.0, volume=5000)
    score, _ = score_retest_entry(
        "long", ch, candle, [candle],
        vol_multiplier=2.5,
        require_confirmed_structure=True,
    )
    assert score >= 70


def test_neutral_trend_rejected_when_confirmed_required():
    ch = ChannelUpdateResult(
        bull_retest=True,
        high_volume=True,
        volume_ratio=5.0,
        retest_bars_elapsed=3,
        trend_structure=TrendStructure.NEUTRAL,
    )
    candle = _candle(open=100.0, close=101.0)
    score, breakdown = score_retest_entry(
        "long", ch, candle, [candle],
        vol_multiplier=2.5,
        require_confirmed_structure=True,
    )
    assert score == 0
    assert "structure" in breakdown.get("reject", "")


def test_retest_uses_breakout_volume_when_retest_bar_is_weak():
    ch = ChannelUpdateResult(
        bull_retest=True,
        high_volume=True,
        volume_ratio=0.4,
        breakout_volume_ratio=5.0,
        retest_bars_elapsed=3,
        trend_structure=TrendStructure.NEUTRAL,
    )
    candle = _candle(open=100.0, close=101.0, volume=500)
    score, breakdown = score_retest_entry(
        "long", ch, candle, [candle],
        vol_multiplier=2.5,
        require_confirmed_structure=False,
    )
    assert score >= 50
    assert breakdown.get("volume", 0) >= 12


def test_stale_retest_scores_lower():
    ch = ChannelUpdateResult(
        bear_retest=True,
        high_volume=True,
        volume_ratio=3.7,
        breakout_volume_ratio=3.7,
        retest_bars_elapsed=22,
        trend_structure=TrendStructure.DOWNTREND,
    )
    candle = _candle(open=100.0, close=99.0)
    score, breakdown = score_retest_entry(
        "short", ch, candle, [candle],
        vol_multiplier=2.5,
        require_confirmed_structure=True,
    )
    assert breakdown.get("retest_stale") is True
    assert breakdown.get("retest", 15) <= 5
    assert score < 77

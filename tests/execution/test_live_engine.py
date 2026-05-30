"""Tests for live engine candle helpers."""

from execution.live_engine import _closed_bar, _merge_candles
from market_data.models.candle import Candle


def _c(ts: int, close: float) -> Candle:
    return Candle(timestamp=ts, open=close, high=close, low=close, close=close, volume=1.0)


def test_closed_bar_uses_second_to_last():
    candles = [_c(1, 10), _c(2, 20), _c(3, 30)]
    assert _closed_bar(candles).timestamp == 2


def test_merge_candles_dedupes_by_timestamp():
    a = [_c(1, 1), _c(2, 2)]
    b = [_c(2, 99), _c(3, 3)]
    merged = _merge_candles(a, b)
    assert [c.timestamp for c in merged] == [1, 2, 3]
    assert merged[1].close == 99

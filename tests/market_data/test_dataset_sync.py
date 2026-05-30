from market_data.dataset_sync import (
    compute_missing_ranges,
    merge_ranges,
    MS_PER_DAY,
)
from market_data.models.candle import Candle


def _candle(ts: int) -> Candle:
    return Candle(
        timestamp=ts,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
    )


def test_tail_stale_when_no_end_time():
    base = 1_700_000_000_000
    candles = [_candle(base), _candle(base + MS_PER_DAY)]
    now = base + int(3 * MS_PER_DAY)
    ranges = compute_missing_ranges(
        candles,
        start_time=None,
        end_time=None,
        max_stale_days=1.0,
        now=now,
    )
    assert len(ranges) == 1
    assert ranges[0][0] == candles[-1].timestamp + 1
    assert ranges[0][1] == now


def test_internal_gap_over_one_day():
    base = 1_700_000_000_000
    candles = [
        _candle(base),
        _candle(base + MS_PER_DAY),
        _candle(base + 3 * MS_PER_DAY),
    ]
    ranges = compute_missing_ranges(
        candles,
        start_time=None,
        end_time=None,
        max_stale_days=999.0,
        now=base + 4 * MS_PER_DAY,
    )
    gap_ranges = [r for r in ranges if r[0] == base + MS_PER_DAY + 1]
    assert len(gap_ranges) == 1
    assert gap_ranges[0][1] == base + 3 * MS_PER_DAY - 1


def test_empty_dataset_requests_initial_window():
    now = 1_700_000_000_000
    ranges = compute_missing_ranges([], now=now)
    assert len(ranges) == 1
    assert ranges[0][1] == now


def test_merge_ranges():
    merged = merge_ranges([(1, 5), (4, 10), (20, 30)])
    assert merged == [(1, 10), (20, 30)]

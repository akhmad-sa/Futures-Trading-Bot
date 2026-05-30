"""
Local dataset freshness checks and incremental sync for backtests.

Before each backtest run, inspect Parquet coverage (time range + gaps).
If the tail is more than *max_stale_days* behind UTC now, or internal
gaps exceed one day, fetch missing candles and append to storage.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from market_data.models.candle import Candle

logger = logging.getLogger(__name__)

MS_PER_DAY = 86_400_000


@dataclass
class DatasetInfo:
    """Summary of a local Parquet candle dataset."""

    exchange: str
    symbol: str
    timeframe: str
    path: str
    exists: bool
    count: int
    min_ts: Optional[int]
    max_ts: Optional[int]
    staleness_days: Optional[float]

    @property
    def min_label(self) -> str:
        return format_ts_ms(self.min_ts)

    @property
    def max_label(self) -> str:
        return format_ts_ms(self.max_ts)


def format_ts_ms(ts_ms: Optional[int]) -> str:
    if ts_ms is None:
        return "n/a"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def now_ms() -> int:
    return int(time.time() * 1000)


def compute_missing_ranges(
    candles: List[Candle],
    *,
    start_time: Optional[int],
    end_time: Optional[int],
    max_stale_days: float = 1.0,
    max_internal_gap_days: float = 1.0,
    now: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """
    Return (start_ms, end_ms) ranges that should be downloaded and appended.

    Includes: head before first candle, tail after last (staleness or end_time),
    and internal gaps wider than *max_internal_gap_days*.
    """
    if not candles:
        effective_end = end_time if end_time is not None else (now or now_ms())
        effective_start = start_time if start_time is not None else (
            effective_end - int(30 * MS_PER_DAY)
        )
        return [(effective_start, effective_end)]

    now_val = now if now is not None else now_ms()
    local_min = candles[0].timestamp
    local_max = candles[-1].timestamp
    max_stale_ms = int(max_stale_days * MS_PER_DAY)
    max_gap_ms = int(max_internal_gap_days * MS_PER_DAY)

    ranges: List[Tuple[int, int]] = []

    if start_time is not None and start_time < local_min:
        ranges.append((start_time, local_min - 1))

    effective_end = end_time if end_time is not None else now_val
    tail_gap = effective_end - local_max
    if tail_gap > max_stale_ms:
        ranges.append((local_max + 1, effective_end))
    elif end_time is not None and end_time > local_max:
        ranges.append((local_max + 1, end_time))

    for i in range(len(candles) - 1):
        gap = candles[i + 1].timestamp - candles[i].timestamp
        if gap > max_gap_ms:
            gap_start = candles[i].timestamp + 1
            gap_end = candles[i + 1].timestamp - 1
            if gap_start <= gap_end:
                ranges.append((gap_start, gap_end))

    return merge_ranges(ranges)


def merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping (start, end) millisecond intervals."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged: List[Tuple[int, int]] = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def build_dataset_info(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    path: str,
    candles: Optional[List[Candle]],
) -> DatasetInfo:
    exists = candles is not None and len(candles) > 0
    if not exists:
        return DatasetInfo(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            path=path,
            exists=False,
            count=0,
            min_ts=None,
            max_ts=None,
            staleness_days=None,
        )
    assert candles is not None
    max_ts = candles[-1].timestamp
    staleness = (now_ms() - max_ts) / MS_PER_DAY
    return DatasetInfo(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        path=path,
        exists=True,
        count=len(candles),
        min_ts=candles[0].timestamp,
        max_ts=max_ts,
        staleness_days=staleness,
    )


def log_dataset_audit(info: DatasetInfo) -> None:
    if not info.exists:
        logger.info(
            "[DATASET] %s %s %s — no local file (%s)",
            info.exchange,
            info.symbol,
            info.timeframe,
            info.path,
        )
        return
    logger.info(
        "[DATASET] %s %s %s — %d candles | %s → %s | tail %.2f days ago",
        info.exchange,
        info.symbol,
        info.timeframe,
        info.count,
        info.min_label,
        info.max_label,
        info.staleness_days or 0.0,
    )


def log_sync_plan(
    info: DatasetInfo,
    ranges: List[Tuple[int, int]],
    *,
    max_stale_days: float,
) -> None:
    if not ranges:
        logger.info(
            "[DATASET] %s %s %s — up to date (staleness ≤ %.1f day)",
            info.symbol,
            info.timeframe,
            info.exchange,
            max_stale_days,
        )
        return
    for start, end in ranges:
        logger.info(
            "[DATASET] %s %s %s — sync %s → %s (append)",
            info.symbol,
            info.timeframe,
            info.exchange,
            format_ts_ms(start),
            format_ts_ms(end),
        )

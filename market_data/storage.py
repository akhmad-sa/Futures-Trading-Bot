"""
Parquet storage utilities.
"""
import os
from typing import List

import pyarrow as pa
import pyarrow.parquet as pq

from .models import Candle


def save_candles_to_parquet(
    candles: List[Candle],
    file_path: str,
    append: bool = True,
) -> None:
    """Save candles to a Parquet file."""
    timestamps = [c.timestamp for c in candles]
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]

    table = pa.table(
        {
            "timestamp": pa.array(timestamps, type=pa.int64()),
            "open": pa.array(opens, type=pa.float64()),
            "high": pa.array(highs, type=pa.float64()),
            "low": pa.array(lows, type=pa.float64()),
            "close": pa.array(closes, type=pa.float64()),
            "volume": pa.array(volumes, type=pa.float64()),
        }
    )

    if append and os.path.exists(file_path):
        existing = pq.read_table(file_path)
        combined = pa.concat_tables([existing, table])
        pq.write_table(combined, file_path)
    else:
        pq.write_table(table, file_path)


def load_candles_from_parquet(file_path: str) -> List[Candle]:
    """Load candles from a Parquet file."""
    table = pq.read_table(file_path)
    candles: List[Candle] = []
    for i in range(table.num_rows):
        candle = Candle(
            timestamp=int(table.column("timestamp")[i].as_py()),
            open=float(table.column("open")[i].as_py()),
            high=float(table.column("high")[i].as_py()),
            low=float(table.column("low")[i].as_py()),
            close=float(table.column("close")[i].as_py()),
            volume=float(table.column("volume")[i].as_py()),
        )
        candles.append(candle)
    return candles

"""
Reusable historical market data ingestion module.

Supports CSV and Parquet loading, candle normalization, timeframe
validation, missing candle handling, and async compatibility.
All loaded candles are injected into the central MarketDataService cache.
"""

import asyncio
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

from core.market_data.service import MarketDataService
from core.models.candle import Candle


# ---------------------------------------------------------------------------
# Timeframe helpers
# ---------------------------------------------------------------------------

_TIMEFRAME_MS: Dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


def get_interval_ms(timeframe: str) -> int:
    """Return expected candle interval in milliseconds for a given timeframe string."""
    interval = _TIMEFRAME_MS.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return interval


# ---------------------------------------------------------------------------
# Default column mapping (CSV / Parquet)
# ---------------------------------------------------------------------------

_DEFAULT_COLUMN_MAP: Dict[str, str] = {
    "timestamp": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


# ---------------------------------------------------------------------------
# Ingestion class
# ---------------------------------------------------------------------------

class HistoricalDataIngestion:
    """Load historical candle data from files and inject into MarketDataService."""

    def __init__(self, service: MarketDataService) -> None:
        self._service = service

    # ------------------------------------------------------------------
    # Public ingestion methods
    # ------------------------------------------------------------------

    async def ingest_csv(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        file_path: str,
        column_map: Optional[Dict[str, str]] = None,
        fill_missing: bool = True,
        timestamp_multiplier: int = 1,  # 1 for ms, 1000 if source is seconds
        **csv_kwargs,
    ) -> List[Candle]:
        """
        Load candles from a CSV file, normalise, validate, and inject into the service.

        Parameters
        ----------
        exchange : str
            Exchange identifier (e.g. "binance").
        symbol : str
            Trading pair symbol (e.g. "BTC/USDT").
        timeframe : str
            Expected candle timeframe (e.g. "1h").
        file_path : str
            Path to the CSV file.
        column_map : dict, optional
            Mapping from CSV column names to Candle field names.
            Default maps ``['timestamp','open','high','low','close','volume']``.
        fill_missing : bool
            If True, fill gaps with synthetic candles (close of previous candle, volume 0).
        timestamp_multiplier : int
            Multiply the raw timestamp column by this value to obtain milliseconds.
            For source timestamps in seconds, pass 1000. Default 1 (already ms).
        **csv_kwargs : any
            Additional keyword arguments passed to ``pd.read_csv``.

        Returns
        -------
        List[Candle]
            The list of normalised, validated, and injected candles.
        """
        # Read CSV in a thread pool to avoid blocking the event loop
        df = await asyncio.to_thread(
            pd.read_csv, file_path, **csv_kwargs
        )

        return await self._process_dataframe(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            df=df,
            column_map=column_map,
            fill_missing=fill_missing,
            timestamp_multiplier=timestamp_multiplier,
        )

    async def ingest_parquet(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        file_path: str,
        column_map: Optional[Dict[str, str]] = None,
        fill_missing: bool = True,
        timestamp_multiplier: int = 1,
        **parquet_kwargs,
    ) -> List[Candle]:
        """
        Load candles from a Parquet file, normalise, validate, and inject.

        Parameters are identical to :meth:`ingest_csv` except the file format.
        """
        df = await asyncio.to_thread(
            pd.read_parquet, file_path, **parquet_kwargs
        )

        return await self._process_dataframe(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            df=df,
            column_map=column_map,
            fill_missing=fill_missing,
            timestamp_multiplier=timestamp_multiplier,
        )

    # ------------------------------------------------------------------
    # Internal processing pipeline
    # ------------------------------------------------------------------

    async def _process_dataframe(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        column_map: Optional[Dict[str, str]],
        fill_missing: bool,
        timestamp_multiplier: int,
    ) -> List[Candle]:
        """Normalise, validate, optionally fill gaps, and inject into service."""
        # 1. Normalise column names
        df = self._normalise_columns(df, column_map or _DEFAULT_COLUMN_MAP)

        # 2. Convert to list of Candle objects (raw, unsorted)
        raw_candles = self._df_to_candles(
            df, symbol, timeframe, exchange, timestamp_multiplier
        )

        if not raw_candles:
            return []

        # 3. Sort by timestamp and deduplicate
        raw_candles.sort(key=lambda c: c.timestamp)
        deduped = self._deduplicate(raw_candles)

        # 4. Validate timeframe consistency
        self._validate_timeframe_consistency(deduped, timeframe)

        # 5. Optionally fill missing candles
        if fill_missing:
            deduped = self._fill_missing_candles(deduped, timeframe)

        # 6. Inject into the shared cache
        await self._inject_into_service(
            exchange, symbol, timeframe, deduped
        )

        return deduped

    # ------------------------------------------------------------------
    # Column normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_columns(
        df: pd.DataFrame, column_map: Dict[str, str]
    ) -> pd.DataFrame:
        """
        Rename columns so the DataFrame always contains the canonical fields:
        ``timestamp``, ``open``, ``high``, ``low``, ``close``, ``volume``.
        """
        rename = {}
        for src_field, target_field in column_map.items():
            if src_field in df.columns:
                rename[src_field] = target_field
        return df.rename(columns=rename)

    # ------------------------------------------------------------------
    # DataFrame → Candle list
    # ------------------------------------------------------------------

    @staticmethod
    def _df_to_candles(
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        exchange: str,
        multiplier: int,
    ) -> List[Candle]:
        """Convert a DataFrame with canonical columns into Candle objects."""
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"DataFrame is missing required columns: {missing}"
            )

        candles: List[Candle] = []
        for _, row in df.iterrows():
            timestamp_raw = row["timestamp"]
            # Normalise timestamp to int
            if isinstance(timestamp_raw, float) and timestamp_raw.is_integer():
                timestamp_raw = int(timestamp_raw)
            elif isinstance(timestamp_raw, str):
                # Try to parse ISO format
                try:
                    dt = pd.Timestamp(timestamp_raw).to_pydatetime()
                    timestamp_raw = int(dt.timestamp() * 1000)
                except Exception:
                    raise ValueError(
                        f"Cannot parse timestamp column value: {timestamp_raw}"
                    )
            else:
                timestamp_raw = int(timestamp_raw)

            ts_ms = timestamp_raw * multiplier

            candle = Candle(
                timestamp=ts_ms,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                symbol=symbol,
                timeframe=timeframe,
                exchange=exchange,
            )
            candles.append(candle)

        return candles

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(candles: List[Candle]) -> List[Candle]:
        """Remove candles with duplicate timestamps (keep first occurrence)."""
        seen: set[int] = set()
        result: List[Candle] = []
        for c in candles:
            if c.timestamp not in seen:
                seen.add(c.timestamp)
                result.append(c)
        return result

    # ------------------------------------------------------------------
    # Timeframe validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_timeframe_consistency(
        candles: List[Candle], timeframe: str
    ) -> None:
        """
        Verify that the difference between consecutive timestamps matches the
        expected interval (within a 1 % tolerance).

        Raises ``ValueError`` if a gap or inconsistent interval is detected.
        """
        if len(candles) < 2:
            return

        expected_ms = get_interval_ms(timeframe)
        tolerance = 0.01 * expected_ms

        for i in range(1, len(candles)):
            gap = candles[i].timestamp - candles[i - 1].timestamp
            if gap <= 0:
                raise ValueError(
                    f"Timestamps not strictly increasing at index {i}: "
                    f"{candles[i-1].timestamp} -> {candles[i].timestamp}"
                )
            if abs(gap - expected_ms) > tolerance:
                # Allow first gap to be shorter (partial candle) – just warn
                if i == 1:
                    import warnings

                    warnings.warn(
                        f"First candle gap ({gap} ms) differs significantly from "
                        f"expected {expected_ms} ms. This may indicate incomplete data."
                    )
                else:
                    raise ValueError(
                        f"Interval mismatch at index {i}: expected {expected_ms} ms, "
                        f"got {gap} ms (differs by {abs(gap - expected_ms)} ms)."
                    )

    # ------------------------------------------------------------------
    # Missing candle filling
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_missing_candles(
        candles: List[Candle], timeframe: str
    ) -> List[Candle]:
        """
        Fill gaps with synthetic candles whose OHLC values equal the previous
        close and volume is zero.
        """
        if len(candles) < 2:
            return candles

        interval_ms = get_interval_ms(timeframe)
        filled: List[Candle] = []

        for i in range(len(candles) - 1):
            current = candles[i]
            next_candle = candles[i + 1]
            filled.append(current)

            gap = next_candle.timestamp - current.timestamp
            missing_count = gap // interval_ms - 1

            for j in range(missing_count):
                synthetic_ts = current.timestamp + (j + 1) * interval_ms
                synthetic = Candle(
                    timestamp=synthetic_ts,
                    open=current.close,
                    high=current.close,
                    low=current.close,
                    close=current.close,
                    volume=0.0,
                    symbol=current.symbol,
                    timeframe=current.timeframe,
                    exchange=current.exchange,
                )
                filled.append(synthetic)

        filled.append(candles[-1])
        return filled

    # ------------------------------------------------------------------
    # Injection into MarketDataService
    # ------------------------------------------------------------------

    async def _inject_into_service(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
    ) -> None:
        """Add the candles to the service's shared cache."""
        await self._service.add_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

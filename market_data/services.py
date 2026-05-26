"""
Centralized market data service.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Callable

from .models import Candle


class MarketDataService(ABC):
    """Abstract interface for retrieving candle data."""

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 500,
    ) -> List[Candle]:
        ...

    @abstractmethod
    async def subscribe(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[Candle], None],
    ):
        """Subscribe to real‑time candle updates (optional)."""
        ...


class HistoricalCsvService(MarketDataService):
    """Reads candle data from a CSV file."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 500,
    ) -> List[Candle]:
        import csv

        candles: List[Candle] = []
        with open(self.file_path, "r") as f:
            reader = csv.reader(f)
            # skip header if present
            header = next(reader, None)
            for row in reader:
                try:
                    ts = int(row[0])
                    if start is not None and ts < start:
                        continue
                    if end is not None and ts > end:
                        continue
                    candle = Candle.from_list([float(x) for x in row[:6]])
                    candles.append(candle)
                except (IndexError, ValueError):
                    continue
        return candles[-limit:] if limit else candles

    async def subscribe(self, symbol: str, timeframe: str, callback):
        raise NotImplementedError(
            "Historical service does not support real‑time subscription."
        )


class ParquetDataService(MarketDataService):
    """Reads candle data from Parquet files."""

    def __init__(self, directory: str):
        self.directory = directory

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 500,
    ) -> List[Candle]:
        import os
        import pyarrow.parquet as pq
        import pyarrow as pa

        file_path = os.path.join(
            self.directory, f"{symbol}_{timeframe}.parquet"
        )
        if not os.path.exists(file_path):
            return []

        table = pq.read_table(file_path)
        # Apply basic filtering on timestamp column (not optimised)
        # Here we simply return all candles, default limit
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
            if start is not None and candle.timestamp < start:
                continue
            if end is not None and candle.timestamp > end:
                continue
            candles.append(candle)
        return candles[-limit:] if limit else candles

    async def subscribe(self, symbol: str, timeframe: str, callback):
        raise NotImplementedError(
            "Parquet service does not support live updates."
        )


class LiveWebSocketService(MarketDataService):
    """Live market data from exchange websocket."""

    def __init__(self, exchange_name: str, api_key: str = "", api_secret: str = ""):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self._store: List[Candle] = []  # in‑memory cache

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 500,
    ) -> List[Candle]:
        # In a real implementation fetch from REST API.
        # For now return whatever we have cached.
        candles = self._store
        if start is not None:
            candles = [c for c in candles if c.timestamp >= start]
        if end is not None:
            candles = [c for c in candles if c.timestamp <= end]
        return candles[-limit:] if limit else candles

    async def subscribe(self, symbol: str, timeframe: str, callback):
        # Start websocket and feed candles to callback
        # Placeholder – real implementation would use ccxt or similar
        raise NotImplementedError("LiveWebSocketService.subscribe() not yet implemented")

"""
Market data layer – unified access to historical and realtime candle data.

Provides a centralized ``MarketDataService`` that abstracts the data
source (live exchange, database, file, or in‑memory list) from consumers.
"""

from .services.market_data_service import MarketDataService
from .models.candle import Candle

__all__ = [
    "MarketDataService",
    "Candle",
]

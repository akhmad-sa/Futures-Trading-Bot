"""
Abstract base class for exchange implementations.
"""

from abc import ABC, abstractmethod
from typing import Callable


class BaseExchange(ABC):
    """Interface that all exchange adapters must implement."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish REST and WebSocket connections."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close all connections."""

    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> list:
        """Return OHLCV candles."""

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float = 0.0,
    ) -> dict:
        """Place an order and return exchange response."""

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> None:
        """Cancel an open order."""

    @abstractmethod
    async def fetch_position(self, symbol: str) -> dict:
        """Return the current position for a symbol."""

    @abstractmethod
    async def fetch_balance(self) -> dict:
        """Return account balance."""

    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback: Callable) -> None:
        """Subscribe to real‑time ticker updates."""

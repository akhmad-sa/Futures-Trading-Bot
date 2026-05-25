"""
Binance Futures stub – adapters can be added later.
"""

from .base import BaseExchange


class BinanceExchange(BaseExchange):
    """Placeholder for Binance Futures integration."""

    async def connect(self) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> list:
        raise NotImplementedError

    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float = 0.0,
    ) -> dict:
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str) -> None:
        raise NotImplementedError

    async def fetch_position(self, symbol: str) -> dict:
        raise NotImplementedError

    async def subscribe_ticker(self, symbol: str, callback) -> None:
        raise NotImplementedError

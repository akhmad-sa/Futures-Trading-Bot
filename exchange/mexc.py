"""
MEXC Futures exchange implementation using ccxt async.
"""

import ccxt.async_support as ccxt
from decimal import Decimal
from .base import BaseExchange


class MEXCExchange(BaseExchange):
    """Adapter for MEXC Futures (perpetual swaps)."""

    def __init__(self, config) -> None:
        self.config = config
        self.exchange = ccxt.mexc(
            {
                "apiKey": config.mexc_api_key,
                "secret": config.mexc_api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            }
        )

    async def connect(self) -> None:
        """Load markets (and optionally start WebSocket)."""
        await self.exchange.load_markets()

    async def disconnect(self) -> None:
        await self.exchange.close()

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> list:
        return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float = 0.0,
    ) -> dict:
        return await self.exchange.create_order(symbol, order_type, side, amount, price)

    async def cancel_order(self, symbol: str, order_id: str) -> None:
        await self.exchange.cancel_order(order_id, symbol)

    async def fetch_position(self, symbol: str) -> dict:
        positions = await self.exchange.fetch_positions([symbol])
        return positions[0] if positions else {}

    async def fetch_balance(self) -> dict:
        return await self.exchange.fetch_balance()

    async def subscribe_ticker(self, symbol: str, callback) -> None:
        """Placeholder – real WebSocket integration is implemented in WebSocketManager."""
        raise NotImplementedError("Use WebSocketManager for streaming tickers")

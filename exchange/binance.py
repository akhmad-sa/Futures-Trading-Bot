"""
Binance Futures exchange implementation using ccxt async.
"""

import logging
from typing import Callable

import ccxt.async_support as ccxt

from .base import BaseExchange
from .models import Balance, Position

logger = logging.getLogger(__name__)


class BinanceExchange(BaseExchange):
    """Adapter for Binance Futures (perpetual swaps)."""

    exchange_name = "binance"
    _ws_url = "wss://fstream.binance.com/ws"

    def __init__(self, config) -> None:
        super().__init__(config)
        self.exchange = ccxt.binance({
            "apiKey": self.config.get("api_key", ""),
            "secret": self.config.get("api_secret", ""),
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

    async def connect(self) -> None:
        """Load markets."""
        await self.exchange.load_markets()

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

    async def fetch_position(self, symbol: str) -> Position:
        positions = await self.exchange.fetch_positions([symbol])
        if not positions:
            return Position(
                symbol=symbol, side="neutral", size=0.0, entry_price=0.0,
                mark_price=0.0, pnl=0.0, leverage=1, liquidation_price=0.0,
                margin=0.0, timestamp=datetime.utcnow(), exchange="binance"
            )
        p = positions[0]
        return Position(
            symbol=p["symbol"],
            side="long" if p.get("side") == "long" else "short",
            size=p.get("contracts", p.get("size", 0)),
            entry_price=p.get("entryPrice", 0.0),
            mark_price=p.get("markPrice", 0.0),
            pnl=p.get("unrealizedPnl", 0.0),
            leverage=p.get("leverage", 1),
            liquidation_price=p.get("liquidationPrice", 0.0),
            margin=p.get("initialMargin", 0.0),
            timestamp=datetime.utcnow(),
            exchange="binance",
        )

    async def fetch_balance(self) -> Balance:
        bal = await self.exchange.fetch_balance()
        total = bal["total"].get("USDT", 0)
        free = bal["free"].get("USDT", 0)
        used = bal["used"].get("USDT", 0)
        return Balance(
            total=total, free=free, used=used, currency="USDT", exchange="binance"
        )

    async def on_websocket_message(self, message: dict):
        """Process raw websocket message and enqueue it for the dispatcher."""
        if self._dispatcher:
            # Add a standardized event_type for the dispatcher
            if 'e' in message and 's' in message:
                event_type = f"{message['e']}:{message['s']}"
                message["event_type"] = event_type
                await self._dispatcher.enqueue_message(message)
            else:
                logger.debug("[%s] Received unhandled message: %s", self.exchange_name, message)

    async def subscribe_ticker(self, symbol: str, callback: Callable) -> None:
        """Subscribe to real‑time ticker updates."""
        if not self._ws_manager or not self._dispatcher:
            raise RuntimeError("WebSocket manager not initialized. Call init_websocket() first.")

        try:
            market = self.exchange.market(symbol)
            normalized_symbol = market["id"]
        except Exception:
            logger.error(f"[{self.exchange_name}] Symbol {symbol} not found.")
            return

        channel = f"{normalized_symbol.lower()}@ticker"
        event_type = f"24hrTicker:{normalized_symbol}"

        self._dispatcher.register_handler(event_type, callback)

        payload = {
            "method": "SUBSCRIBE",
            "params": [channel],
            "id": 1  # Using a static ID for simplicity
        }
        await self._ws_manager.subscribe(channel, payload)

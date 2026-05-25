"""
Bybit Futures exchange implementation using ccxt async.
"""

import logging
from datetime import datetime
from typing import Callable

import ccxt.async_support as ccxt

from .base import BaseExchange
from .models import Balance, Position

logger = logging.getLogger(__name__)


class BybitExchange(BaseExchange):
    """Adapter for Bybit Futures (perpetual swaps)."""

    exchange_name = "bybit"
    _ws_url = "wss://stream.bybit.com/v5/public/linear"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.exchange = ccxt.bybit({
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
                margin=0.0, timestamp=datetime.utcnow(), exchange="bybit"
            )
        p = positions[0]
        return Position(
            symbol=p["symbol"],
            side="long" if p["side"] == "long" else "short",
            size=p.get("contracts", p.get("size", 0)),
            entry_price=p.get("entryPrice", 0.0),
            mark_price=p.get("markPrice", 0.0),
            pnl=p.get("unrealizedPnl", 0.0),
            leverage=p.get("leverage", 1),
            liquidation_price=p.get("liquidationPrice", 0.0),
            margin=p.get("initialMargin", 0.0),
            timestamp=datetime.utcnow(),
            exchange="bybit",
        )

    async def fetch_balance(self) -> Balance:
        bal = await self.exchange.fetch_balance()
        total = bal["total"].get("USDT", 0)
        free = bal["free"].get("USDT", 0)
        used = bal["used"].get("USDT", 0)
        return Balance(
            total=total, free=free, used=used, currency="USDT", exchange="bybit"
        )

    async def on_websocket_message(self, message: dict):
        """Process raw websocket message and enqueue it for the dispatcher."""
        if self._dispatcher:
            if "topic" in message:
                # Bybit topics are like "tickers.BTCUSDT"
                topic_parts = message["topic"].split(".")
                if len(topic_parts) == 2:
                    msg_type, symbol = topic_parts
                    event_type = f"{msg_type}:{symbol}"
                    message["event_type"] = event_type
                    await self._dispatcher.enqueue_message(message)
                else:
                    logger.debug("[%s] Received unhandled message: %s", self.exchange_name, message)
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

        channel = f"tickers.{normalized_symbol}"
        event_type = f"tickers:{normalized_symbol}"

        self._dispatcher.register_handler(event_type, callback)

        payload = {"op": "subscribe", "args": [channel]}
        await self._ws_manager.subscribe(channel, payload)

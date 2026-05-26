"""
MEXC Futures exchange implementation using ccxt async.
"""

import logging
from datetime import datetime
from typing import Callable, List, Optional

import ccxt.async_support as ccxt

from .base import BaseExchange
from .models import (
    Balance, Position, Order, Candle, OrderSide, OrderType, OrderStatus, PositionSide
)

logger = logging.getLogger(__name__)


class MEXCExchange(BaseExchange):
    """Adapter for MEXC Futures (perpetual swaps)."""

    exchange_name = "mexc"
    _ws_url = "wss://contract.mexc.com/ws"

    def __init__(self, config) -> None:
        super().__init__(config)
        exchange_config = {
            "apiKey": self.config.mexc_api_key if hasattr(self.config, "mexc_api_key") else self.config.get("api_key", ""),
            "secret": self.config.mexc_api_secret if hasattr(self.config, "mexc_api_secret") else self.config.get("api_secret", ""),
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
        if self.config.get("testnet"):
            self.exchange = ccxt.mexc(exchange_config)
            self.exchange.set_sandbox_mode(True)
        else:
            self.exchange = ccxt.mexc(exchange_config)

    async def connect(self) -> None:
        """Load markets."""
        await self.exchange.load_markets()

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> List[Candle]:
        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [
            Candle(
                timestamp=c[0],
                open=c[1],
                high=c[2],
                low=c[3],
                close=c[4],
                volume=c[5],
            )
            for c in ohlcv
        ]

    def _parse_order(self, order_data: dict) -> Order:
        return Order(
            id=order_data["id"],
            symbol=order_data["symbol"],
            side=OrderSide(order_data["side"]),
            type=OrderType(order_data["type"]),
            status=OrderStatus(order_data["status"]),
            price=order_data.get("price"),
            amount=order_data["amount"],
            filled=order_data["filled"],
            remaining=order_data["remaining"],
            cost=order_data["cost"],
            timestamp=datetime.fromtimestamp(order_data["timestamp"] / 1000),
            exchange=self.exchange_name,
            info=order_data,
        )

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        order_type: OrderType,
        price: Optional[float] = None,
    ) -> Order:
        raw_order = await self.exchange.create_order(
            symbol, order_type.value, side.value, amount, price
        )
        return self._parse_order(raw_order)

    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        raw_order = await self.exchange.cancel_order(order_id, symbol)
        return self._parse_order(raw_order)

    async def fetch_position(self, symbol: str) -> Position:
        positions = await self.exchange.fetch_positions([symbol])
        if not positions:
            return Position(
                symbol=symbol, side=PositionSide.NEUTRAL, size=0.0, entry_price=0.0,
                mark_price=0.0, pnl=0.0, leverage=1, liquidation_price=None,
                margin=0.0, timestamp=datetime.utcnow(), exchange="mexc"
            )
        p = positions[0]
        return Position(
            symbol=p["symbol"],
            side=PositionSide(p.get("side", "neutral")),
            size=p.get("contracts", p.get("size", 0)),
            entry_price=p.get("entryPrice", 0.0),
            mark_price=p.get("markPrice", 0.0),
            pnl=p.get("unrealizedPnl", 0.0),
            leverage=p.get("leverage", 1),
            liquidation_price=p.get("liquidationPrice"),
            margin=p.get("initialMargin", 0.0),
            timestamp=datetime.utcnow(),
            exchange="mexc",
            info=p,
        )

    async def fetch_balance(self) -> Balance:
        bal = await self.exchange.fetch_balance()
        total = bal["total"].get("USDT", 0)
        free = bal["free"].get("USDT", 0)
        used = bal["used"].get("USDT", 0)
        return Balance(
            total=total, free=free, used=used, currency="USDT", exchange="mexc"
        )

    async def on_websocket_message(self, message: dict):
        """Process raw websocket message and enqueue it for the dispatcher."""
        if self._dispatcher:
            if "channel" in message and "data" in message:
                # MEXC channels are like "push.ticker"
                channel = message["channel"]
                symbol = message.get("symbol")
                if channel == "push.ticker" and symbol:
                    event_type = f"ticker:{symbol}"
                    # The actual data is nested
                    data = message["data"]
                    data["event_type"] = event_type
                    await self._dispatcher.enqueue_message(data)
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
            # MEXC uses "BTC_USDT" format for websocket symbols
            normalized_symbol = market["id"].replace("/", "_")
        except Exception:
            logger.error(f"[{self.exchange_name}] Symbol {symbol} not found.")
            return

        channel = "sub.ticker"  # MEXC uses one method for all tickers
        event_type = f"ticker:{normalized_symbol}"

        self._dispatcher.register_handler(event_type, callback)

        payload = {
            "method": channel,
            "param": {"symbol": normalized_symbol}
        }
        # For MEXC, the channel key for the manager is the method + symbol
        await self._ws_manager.subscribe(f"{channel}:{normalized_symbol}", payload)

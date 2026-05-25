"""
Stream handlers for market data and user data WebSocket messages.

Each handler parses incoming messages and dispatches typed events via the EventDispatcher.
"""

import logging
from typing import Any

from exchange.event_dispatcher import EventDispatcher

logger = logging.getLogger(__name__)


class MarketStreamHandler:
    """
    Handles incoming market data messages (ticker, kline, depth, etc.)
    and dispatches them as typed events.
    """

    def __init__(self, dispatcher: EventDispatcher) -> None:
        self._dispatcher = dispatcher

    async def handle_message(self, symbol: str, data: dict[str, Any]) -> None:
        """
        Parse a market data message and dispatch the appropriate event.

        Expected data format (MEXC):
        {
            "e": "24hrTicker",   // event type
            "s": "BTCUSDT",      // symbol
            ...
        }
        """
        event_type = data.get("e", "unknown")
        if event_type == "24hrTicker":
            await self._dispatcher.dispatch("ticker", data)
        elif event_type == "kline":
            await self._dispatcher.dispatch("kline", data)
        elif event_type == "depthUpdate":
            await self._dispatcher.dispatch("depth", data)
        else:
            logger.debug("Unhandled market event type '%s' for %s", event_type, symbol)
            await self._dispatcher.dispatch("market:unknown", data)


class UserStreamHandler:
    """
    Handles incoming user data messages (order updates, balance updates, position updates)
    and dispatches them as typed events.
    """

    def __init__(self, dispatcher: EventDispatcher) -> None:
        self._dispatcher = dispatcher

    async def handle_message(self, listen_key: str, data: dict[str, Any]) -> None:
        """
        Parse a user data message and dispatch the appropriate event.

        Expected data format (MEXC):
        {
            "e": "ORDER_TRADE_UPDATE",   // event type
            ...
        }
        """
        event_type = data.get("e", "unknown")
        if event_type == "ORDER_TRADE_UPDATE":
            await self._dispatcher.dispatch("order_update", data)
        elif event_type == "ACCOUNT_UPDATE":
            await self._dispatcher.dispatch("account_update", data)
        elif event_type == "listenKeyExpired":
            logger.warning("Listen key expired for %s", listen_key)
            await self._dispatcher.dispatch("listen_key_expired", {"listen_key": listen_key})
        else:
            logger.debug("Unhandled user event type '%s' for %s", event_type, listen_key)
            await self._dispatcher.dispatch("user:unknown", data)

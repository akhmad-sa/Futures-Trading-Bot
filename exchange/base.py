"""
Abstract base class for exchange implementations.
Provides a unified interface for all exchanges.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional

import ccxt.async_support as ccxt

from .models import Balance, Position
from websocket.dispatcher import WebsocketDispatcher
from websocket.manager import WebsocketManager

logger = logging.getLogger(__name__)


class BaseExchange(ABC):
    """Interface that all exchange adapters must implement."""

    exchange_name: str = "base"
    _ws_url: str = ""

    def __init__(self, config):
        self.config = config
        self.exchange: Optional[ccxt.async_support.Exchange] = None
        self._ws_manager: Optional[WebsocketManager] = None
        self._dispatcher: Optional[WebsocketDispatcher] = None

    @abstractmethod
    async def connect(self) -> None:
        """Establish REST connections."""

    async def disconnect(self) -> None:
        """Close all connections."""
        if self.exchange:
            await self.exchange.close()
        if self._ws_manager and self._ws_manager._is_running:
            await self._ws_manager.stop()

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
    async def fetch_position(self, symbol: str) -> Position:
        """Return the current position for a symbol."""

    @abstractmethod
    async def fetch_balance(self) -> Balance:
        """Return account balance."""

    def init_websocket(self, dispatcher: WebsocketDispatcher):
        """Initialize and start the WebSocket manager."""
        if not self._ws_url:
            raise NotImplementedError(f"Websocket URL not defined for {self.exchange_name}")

        if self._ws_manager:
            logger.warning("[%s] WebSocket manager already initialized.", self.exchange_name)
            return

        self._dispatcher = dispatcher
        self._ws_manager = WebsocketManager(
            url=self._ws_url,
            exchange_name=self.exchange_name,
            on_message=self.on_websocket_message,
            on_connect=self._on_ws_connect,
        )
        asyncio.create_task(self._ws_manager.start())

    async def _on_ws_connect(self, ws_manager: WebsocketManager):
        """Callback executed on successful websocket connection to resubscribe."""
        logger.info("[%s] WebSocket connected. Resubscribing to channels...", self.exchange_name)
        await ws_manager.resubscribe_all()

    @abstractmethod
    async def on_websocket_message(self, message: dict):
        """Process raw websocket message and enqueue it for the dispatcher."""
        raise NotImplementedError

    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback: Callable) -> None:
        """Subscribe to real‑time ticker updates."""

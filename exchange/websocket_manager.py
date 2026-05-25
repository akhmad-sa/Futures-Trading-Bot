"""
Robust async WebSocket manager for MEXC Futures.

Features:
- Auto reconnect with exponential backoff
- Heartbeat (ping/pong) handling
- Async queues for incoming messages
- Event-driven architecture via EventDispatcher
- Separate market stream and user stream connections
- Graceful shutdown
- Logging
- Error recovery
- Prevent duplicate subscriptions
"""

import asyncio
import json
import logging
from typing import Any, Callable, Optional

import aiohttp

from exchange.event_dispatcher import EventDispatcher
from exchange.stream_handlers import MarketStreamHandler, UserStreamHandler

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages multiple WebSocket connections (market and user streams)
    with automatic reconnection, heartbeat, and duplicate subscription prevention.
    """

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._connections: dict[str, aiohttp.ClientWebSocketResponse] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._subscriptions: dict[str, set[str]] = {}  # stream_type -> set of symbols
        self._event_dispatcher = EventDispatcher()
        self._market_handler = MarketStreamHandler(self._event_dispatcher)
        self._user_handler = UserStreamHandler(self._event_dispatcher)
        self._running = False
        self._reconnect_delay: float = 1.0  # seconds, exponential backoff
        self._max_reconnect_delay: float = 60.0
        self._heartbeat_interval: float = 20.0  # seconds

    async def _ensure_session(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def connect_market_stream(self, symbol: str, url: str) -> None:
        """
        Subscribe to a market data WebSocket stream for a given symbol.

        Prevents duplicate subscriptions.
        """
        if symbol in self._subscriptions.get("market", set()):
            logger.info("Already subscribed to market stream for %s", symbol)
            return

        await self._ensure_session()
        self._subscriptions.setdefault("market", set()).add(symbol)

        # Start the connection task
        task = asyncio.create_task(
            self._run_market_connection(symbol, url)
        )
        self._tasks[f"market:{symbol}"] = task
        logger.info("Market stream connection task started for %s", symbol)

    async def connect_user_stream(self, listen_key: str, url: str) -> None:
        """
        Subscribe to a user data WebSocket stream (orders, balances, positions).

        Prevents duplicate subscriptions.
        """
        if listen_key in self._subscriptions.get("user", set()):
            logger.info("Already subscribed to user stream for listen key %s", listen_key)
            return

        await self._ensure_session()
        self._subscriptions.setdefault("user", set()).add(listen_key)

        task = asyncio.create_task(
            self._run_user_connection(listen_key, url)
        )
        self._tasks[f"user:{listen_key}"] = task
        logger.info("User stream connection task started for listen key %s", listen_key)

    async def _run_market_connection(self, symbol: str, url: str) -> None:
        """Maintain a persistent market WebSocket connection with auto‑reconnect."""
        retry_delay = self._reconnect_delay
        while self._running:
            try:
                ws = await self._session.ws_connect(
                    url,
                    autoclose=False,
                    autoping=False,  # we handle ping/pong manually
                    heartbeat=self._heartbeat_interval,
                )
                self._connections[f"market:{symbol}"] = ws
                retry_delay = self._reconnect_delay  # reset on success
                logger.info("Market WebSocket connected for %s", symbol)

                # Start heartbeat task
                heartbeat_task = asyncio.create_task(
                    self._heartbeat(ws, f"market:{symbol}")
                )

                # Listen for messages
                await self._listen_market(ws, symbol)

                # If we exit the listen loop, connection was closed
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            except asyncio.CancelledError:
                logger.info("Market connection task cancelled for %s", symbol)
                break
            except Exception as exc:
                logger.error(
                    "Market WebSocket error for %s: %s. Reconnecting in %.1f seconds",
                    symbol,
                    exc,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, self._max_reconnect_delay)

    async def _run_user_connection(self, listen_key: str, url: str) -> None:
        """Maintain a persistent user data WebSocket connection with auto‑reconnect."""
        retry_delay = self._reconnect_delay
        while self._running:
            try:
                ws = await self._session.ws_connect(
                    url,
                    autoclose=False,
                    autoping=False,
                    heartbeat=self._heartbeat_interval,
                )
                self._connections[f"user:{listen_key}"] = ws
                retry_delay = self._reconnect_delay
                logger.info("User WebSocket connected for listen key %s", listen_key)

                heartbeat_task = asyncio.create_task(
                    self._heartbeat(ws, f"user:{listen_key}")
                )

                await self._listen_user(ws, listen_key)

                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            except asyncio.CancelledError:
                logger.info("User connection task cancelled for %s", listen_key)
                break
            except Exception as exc:
                logger.error(
                    "User WebSocket error for %s: %s. Reconnecting in %.1f seconds",
                    listen_key,
                    exc,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, self._max_reconnect_delay)

    async def _listen_market(self, ws: aiohttp.ClientWebSocketResponse, symbol: str) -> None:
        """Read messages from a market WebSocket and dispatch them."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._market_handler.handle_message(symbol, data)
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON from market stream %s: %s", symbol, exc)
            elif msg.type == aiohttp.WSMsgType.PONG:
                logger.debug("Received pong from market stream %s", symbol)
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.info("Market WebSocket closed for %s", symbol)
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error("Market WebSocket error for %s", symbol)
                break

    async def _listen_user(self, ws: aiohttp.ClientWebSocketResponse, listen_key: str) -> None:
        """Read messages from a user data WebSocket and dispatch them."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._user_handler.handle_message(listen_key, data)
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON from user stream %s: %s", listen_key, exc)
            elif msg.type == aiohttp.WSMsgType.PONG:
                logger.debug("Received pong from user stream %s", listen_key)
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.info("User WebSocket closed for %s", listen_key)
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error("User WebSocket error for %s", listen_key)
                break

    async def _heartbeat(self, ws: aiohttp.ClientWebSocketResponse, conn_id: str) -> None:
        """Send periodic pings to keep the connection alive."""
        try:
            while not ws.closed:
                await asyncio.sleep(self._heartbeat_interval)
                await ws.ping()
                logger.debug("Sent ping to %s", conn_id)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Heartbeat error for %s: %s", conn_id, exc)

    async def disconnect(self, stream_type: str, identifier: str) -> None:
        """
        Disconnect a specific stream.

        stream_type: 'market' or 'user'
        identifier: symbol for market, listen_key for user
        """
        conn_key = f"{stream_type}:{identifier}"
        ws = self._connections.pop(conn_key, None)
        if ws:
            await ws.close()
        task = self._tasks.pop(conn_key, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Remove from subscriptions
        if stream_type in self._subscriptions:
            self._subscriptions[stream_type].discard(identifier)
        logger.info("Disconnected %s stream for %s", stream_type, identifier)

    async def close_all(self) -> None:
        """Gracefully close all connections and cancel all tasks."""
        self._running = False
        for conn_key in list(self._connections.keys()):
            ws = self._connections.pop(conn_key, None)
            if ws:
                await ws.close()
        for task_key in list(self._tasks.keys()):
            task = self._tasks.pop(task_key, None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("All WebSocket connections closed")

    def register_event_callback(self, event_type: str, callback: Callable) -> None:
        """Register a callback for a specific event type."""
        self._event_dispatcher.register(event_type, callback)

    def unregister_event_callback(self, event_type: str, callback: Callable) -> None:
        """Unregister a callback for a specific event type."""
        self._event_dispatcher.unregister(event_type, callback)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Mark the manager as running (should be called before connecting)."""
        self._running = True
        logger.info("WebSocket manager started")

    def stop(self) -> None:
        """Mark the manager as stopped (triggers graceful shutdown)."""
        self._running = False
        logger.info("WebSocket manager stopping")

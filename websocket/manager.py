"""
Manages WebSocket connections, including subscriptions, automatic reconnection,
and message dispatching.
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class WebsocketManager:
    """
    Manages a single WebSocket connection, including subscriptions,
    automatic reconnection, and message dispatching.
    """

    def __init__(
        self,
        url: str,
        exchange_name: str,
        on_message: Callable,
        on_connect: Callable,
    ):
        self._url = url
        self._exchange_name = exchange_name
        self._on_message = on_message
        self._on_connect = on_connect
        self._subscriptions: Dict[str, Any] = {}
        self._connection: websockets.WebSocketClientProtocol | None = None
        self._is_running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 1.0  # Initial delay in seconds

    async def start(self):
        """Start the WebSocket connection and message handling loop."""
        if self._is_running:
            logger.warning("[%s] WebSocket manager already running.", self._exchange_name)
            return
        self._is_running = True
        asyncio.create_task(self._connection_loop())

    async def stop(self):
        """Stop the WebSocket connection gracefully."""
        self._is_running = False
        if self._connection and self._connection.open:
            await self._connection.close()
        logger.info("[%s] WebSocket manager stopped.", self._exchange_name)

    async def subscribe(self, channel: str, payload: Dict[str, Any]):
        """Subscribe to a channel."""
        if channel in self._subscriptions:
            logger.debug("[%s] Already subscribed to channel '%s'", self._exchange_name, channel)
            return

        self._subscriptions[channel] = payload
        if self._connection and self._connection.open:
            await self._send_subscription(payload)

    async def unsubscribe(self, channel: str, payload: Dict[str, Any]):
        """Unsubscribe from a channel."""
        if channel not in self._subscriptions:
            return

        del self._subscriptions[channel]
        if self._connection and self._connection.open:
            # This payload should be the unsubscribe equivalent of the subscribe payload
            await self._send_unsubscription(payload)

    async def _send_subscription(self, payload: Dict[str, Any]):
        try:
            await self._connection.send(json.dumps(payload))
            logger.info("[%s] Subscribed with payload: %s", self._exchange_name, payload)
        except ConnectionClosed:
            logger.warning("[%s] Connection closed while sending subscription.", self._exchange_name)
        except Exception as e:
            logger.error("[%s] Error sending subscription: %s", self._exchange_name, e)

    async def _send_unsubscription(self, payload: Dict[str, Any]):
        try:
            await self._connection.send(json.dumps(payload))
            logger.info("[%s] Unsubscribed with payload: %s", self._exchange_name, payload)
        except ConnectionClosed:
            logger.warning("[%s] Connection closed while sending unsubscription.", self._exchange_name)
        except Exception as e:
            logger.error("[%s] Error sending unsubscription: %s", self._exchange_name, e)

    async def _connection_loop(self):
        while self._is_running:
            try:
                async with websockets.connect(self._url) as websocket:
                    self._connection = websocket
                    self._reconnect_attempts = 0
                    self._reconnect_delay = 1.0
                    logger.info("[%s] WebSocket connected to %s", self._exchange_name, self._url)

                    # Call the on_connect callback, which can handle resubscriptions
                    await self._on_connect(self)

                    await self._message_handler_loop()

            except (ConnectionClosed, OSError) as e:
                logger.warning("[%s] WebSocket connection lost: %s", self._exchange_name, e)
            except Exception as e:
                logger.error("[%s] WebSocket error: %s", self._exchange_name, e, exc_info=True)
            finally:
                self._connection = None
                if self._is_running:
                    await self._reconnect()

    async def _message_handler_loop(self):
        while self._is_running:
            try:
                message = await self._connection.recv()
                await self._on_message(json.loads(message))
            except ConnectionClosed:
                # This is expected when the connection is lost, handled by the outer loop
                raise
            except Exception as e:
                logger.error("[%s] Error processing message: %s", self._exchange_name, e)

    async def _reconnect(self):
        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnect_attempts:
            logger.error("[%s] Max reconnect attempts reached. Stopping.", self._exchange_name)
            self._is_running = False
            return

        logger.info(
            "[%s] Reconnecting in %.2f seconds (attempt %d/%d)...",
            self._exchange_name,
            self._reconnect_delay,
            self._reconnect_attempts,
            self._max_reconnect_attempts,
        )
        await asyncio.sleep(self._reconnect_delay)
        # Exponential backoff with jitter
        self._reconnect_delay = min(self._reconnect_delay * 2, 60) + (time.time() % 1)

    async def resubscribe_all(self):
        """Resubscribe to all active channels."""
        if not self._connection or not self._connection.open:
            logger.warning("[%s] Cannot resubscribe, connection is not open.", self._exchange_name)
            return

        logger.info("[%s] Resubscribing to %d channels...", self._exchange_name, len(self._subscriptions))
        for payload in self._subscriptions.values():
            await self._send_subscription(payload)

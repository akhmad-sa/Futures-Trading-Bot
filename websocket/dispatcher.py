"""
Dispatches WebSocket messages from a queue to registered handlers.
"""

import asyncio
import logging
from typing import Callable, Dict, Any, List

logger = logging.getLogger(__name__)


class WebsocketDispatcher:
    """
    Dispatches WebSocket messages from a queue to registered handlers.
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._queue = asyncio.Queue()
        self._is_running = False

    async def start(self):
        """Start the dispatcher loop."""
        if self._is_running:
            logger.warning("Dispatcher already running.")
            return
        self._is_running = True
        asyncio.create_task(self._dispatch_loop())
        logger.info("WebSocket event dispatcher started.")

    async def stop(self):
        """Stop the dispatcher."""
        self._is_running = False
        # Put a sentinel value to unblock the queue
        await self._queue.put(None)
        logger.info("WebSocket event dispatcher stopped.")

    def register_handler(self, event_type: str, handler: Callable):
        """Register a handler for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("Registered handler for event '%s'", event_type)

    def unregister_handler(self, event_type: str, handler: Callable):
        """Unregister a handler."""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug("Unregistered handler for event '%s'", event_type)

    async def enqueue_message(self, message: Dict[str, Any]):
        """Put a message into the dispatch queue."""
        await self._queue.put(message)

    async def _dispatch_loop(self):
        while self._is_running:
            message = await self._queue.get()
            if message is None:  # Sentinel value to stop
                break

            event_type = message.get("event_type")
            if not event_type:
                logger.debug("Could not determine event type for message: %s", message)
                continue

            if event_type in self._handlers:
                for handler in self._handlers[event_type]:
                    try:
                        # Handlers should be async
                        await handler(message)
                    except Exception as e:
                        logger.error("Error in WebSocket handler for event '%s': %s", event_type, e)

            self._queue.task_done()

"""
Event dispatcher for WebSocket messages.

Allows decoupled communication between stream handlers and the rest of the system.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class EventDispatcher:
    """
    Simple event dispatcher that routes events to registered callbacks.

    Events are identified by a string event type.
    """

    def __init__(self) -> None:
        self._callbacks: Dict[str, List[Callable]] = {}

    def register(self, event_type: str, callback: Callable) -> None:
        """Register a callback for a given event type."""
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        if callback not in self._callbacks[event_type]:
            self._callbacks[event_type].append(callback)
            logger.debug("Registered callback for event '%s'", event_type)

    def unregister(self, event_type: str, callback: Callable) -> None:
        """Unregister a callback for a given event type."""
        if event_type in self._callbacks:
            self._callbacks[event_type] = [
                cb for cb in self._callbacks[event_type] if cb is not callback
            ]
            if not self._callbacks[event_type]:
                del self._callbacks[event_type]
            logger.debug("Unregistered callback for event '%s'", event_type)

    async def dispatch(self, event_type: str, data: Any) -> None:
        """
        Dispatch an event to all registered callbacks.

        Callbacks are awaited sequentially. Exceptions are logged but do not
        prevent other callbacks from being called.
        """
        callbacks = self._callbacks.get(event_type, [])
        if not callbacks:
            logger.debug("No callbacks registered for event '%s'", event_type)
            return

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as exc:
                logger.error(
                    "Callback error for event '%s': %s", event_type, exc
                )

"""
Generic async WebSocket manager with auto‑reconnect skeleton.
"""

import asyncio
import json
from typing import Callable, Any

import aiohttp


class WebSocketManager:
    """Manages multiple WebSocket connections and dispatches messages to callbacks."""

    def __init__(self) -> None:
        self._connections: dict[str, aiohttp.ClientWebSocketResponse] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def connect(
        self, url: str, symbol: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Open a WebSocket connection and start listening."""
        await self._ensure_session()
        ws = await self._session.ws_connect(url, autoclose=False, autoping=True)
        self._connections[symbol] = ws
        task = asyncio.create_task(self._listen(ws, callback))
        self._tasks[symbol] = task

    async def _listen(
        self, ws: aiohttp.ClientWebSocketResponse, callback: Callable
    ) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                callback(data)
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break

    async def disconnect(self, symbol: str) -> None:
        """Close a specific connection."""
        ws = self._connections.pop(symbol, None)
        if ws:
            await ws.close()
        task = self._tasks.pop(symbol, None)
        if task:
            task.cancel()

    async def close_all(self) -> None:
        """Close all open connections and the session."""
        for symbol in list(self._connections.keys()):
            await self.disconnect(symbol)
        if self._session:
            await self._session.close()

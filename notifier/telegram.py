"""
Telegram notification service using aiohttp.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from notifier.trading_alerts import (
    format_exit,
    format_near_miss,
    format_open,
    format_partial,
    format_pick,
    format_rejected,
)

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send messages to a Telegram chat."""

    def __init__(self, token: str, chat_id: str) -> None:
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def api_call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call Telegram Bot API; return parsed JSON (may have ok=false)."""
        if not self.token:
            return {"ok": False, "description": "missing bot token"}
        url = f"{self.base_url}/{method}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload or {}) as resp:
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError:
                    text = await resp.text()
                    logger.error("Telegram %s non-JSON (%s): %s", method, resp.status, text)
                    return {"ok": False, "description": text}
                if not data.get("ok"):
                    desc = str(data.get("description", data))
                    if data.get("error_code") == 404:
                        logger.error(
                            "Telegram send failed (404): invalid TELEGRAM_BOT_TOKEN — %s",
                            desc,
                        )
                    else:
                        logger.error(
                            "Telegram %s failed (%s): %s",
                            method,
                            resp.status,
                            desc,
                        )
                return data

    async def send_message(self, text: str, *, chat_id: str | None = None) -> bool:
        """Send a plain text message. Returns True on success."""
        target = str(chat_id or self.chat_id).strip()
        if not self.token or not target:
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        data = await self.api_call(
            "sendMessage",
            {"chat_id": target, "text": text},
        )
        return bool(data.get("ok"))

    async def send_test(self) -> bool:
        """Send a test ping (used by the control bot /test command)."""
        return await self.send_message("🔔 Test notification — bot is reachable.")

    async def send_error(self, text: str) -> None:
        """Notify about an error."""
        await self.send_message(f"❌ Error: {text}")

    async def send_pick(
        self,
        symbol: str,
        side: str,
        score: float,
        *,
        detail: str = "",
    ) -> None:
        await self.send_message(format_pick(symbol, side, score, detail=detail))

    async def send_rejected(self, symbol: str | None, reason: str) -> None:
        await self.send_message(format_rejected(symbol, reason))

    async def send_near_miss(self, symbol: str, score: float) -> None:
        await self.send_message(format_near_miss(symbol, score))

    async def send_entry(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        tp_r: float | None = None,
    ) -> None:
        """Notify about a new position entry (optionally with SL/TP)."""
        if stop_loss is not None and take_profit is not None:
            text = format_open(
                symbol, side, size, price, stop_loss, take_profit, tp_r=tp_r
            )
        else:
            text = f"📈 OPEN {symbol} {side.upper()}\nsize {size:.4f} @ {price:.2f}"
        await self.send_message(text)

    async def send_partial(
        self,
        symbol: str,
        side: str,
        pct: float,
        price: float,
        pnl: float,
        *,
        trigger_r: float = 1.0,
    ) -> None:
        await self.send_message(
            format_partial(symbol, side, pct, price, pnl, trigger_r=trigger_r)
        )

    async def send_exit(
        self,
        symbol: str,
        side: str,
        pnl: float,
        *,
        reason: str = "",
    ) -> None:
        """Notify about a closed position with PnL."""
        await self.send_message(format_exit(symbol, side, pnl, reason=reason))

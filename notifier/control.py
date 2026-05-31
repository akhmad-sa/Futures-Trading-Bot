"""
Telegram command bot for VPS / trading-bot monitoring and systemd control.

Runs as a separate process (``telegram_bot.py``) so it does not block the trader.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from notifier.bot_status import collect_trading_bot_status
from notifier.health import collect_vps_health
from notifier.service_control import ServiceControl
from notifier.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

HELP_TEXT = """🤖 Futures Trading Bot — Control

/health — VPS CPU, memory, disk
/status — trading bot systemd + heartbeat
/test — send a test notification
/bot_start — start trading bot service
/bot_stop — stop trading bot service
/bot_restart — restart trading bot service
/bot_reload — daemon-reload + try-restart service
/help — this message"""


def parse_command(text: str) -> tuple[str, list[str]]:
    """Parse ``/cmd arg1 arg2`` (strip @BotName suffix)."""
    parts = (text or "").strip().split()
    if not parts:
        return "", []
    cmd = parts[0].split("@", 1)[0].lower()
    return cmd, parts[1:]


class TelegramControlBot:
    """Long-polling Telegram bot for ops commands."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        service_name: str,
        heartbeat_path: str,
        poll_seconds: float = 30.0,
        allowed_user_ids: set[str] | None = None,
    ) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.service_name = service_name
        self.heartbeat_path = heartbeat_path
        self.poll_seconds = poll_seconds
        self.allowed_user_ids = allowed_user_ids or set()
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.notifier = TelegramNotifier(token, chat_id)
        self._offset = 0
        self._running = False

    def is_authorized(self, message: dict[str, Any]) -> bool:
        chat = message.get("chat") or {}
        if str(chat.get("id", "")) != self.chat_id:
            return False
        if not self.allowed_user_ids:
            return True
        user = message.get("from") or {}
        return str(user.get("id", "")) in self.allowed_user_ids

    async def run(self) -> None:
        self._running = True
        logger.info(
            "Telegram control bot started (service=%s, chat=%s)",
            self.service_name,
            self.chat_id,
        )
        await self.notifier.send_message(
            "🟢 Telegram control bot online.\nSend /help for commands."
        )
        while self._running:
            try:
                updates = await self._fetch_updates(timeout=int(self.poll_seconds))
                for update in updates:
                    self._offset = max(self._offset, update.get("update_id", 0) + 1)
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Control bot loop error: %s", exc)
                await asyncio.sleep(min(self.poll_seconds, 10.0))

    def stop(self) -> None:
        self._running = False

    async def _fetch_updates(self, *, timeout: int) -> list[dict[str, Any]]:
        params = {
            "offset": self._offset,
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/getUpdates", params=params, timeout=timeout + 10
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("getUpdates failed: %s", text)
                    await asyncio.sleep(5)
                    return []
                data = await resp.json()
        if not data.get("ok"):
            logger.error("getUpdates not ok: %s", data)
            return []
        return data.get("result") or []

    async def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        text = message.get("text") or ""
        if not text.startswith("/"):
            return
        if not self.is_authorized(message):
            logger.warning("Unauthorized Telegram command from chat=%s", message.get("chat"))
            return
        cmd, args = parse_command(text)
        try:
            reply = await self._dispatch(cmd, args)
        except Exception as exc:
            logger.exception("Command failed %s: %s", cmd, exc)
            reply = f"❌ Command failed: {exc}"
        if reply:
            await self.notifier.send_message(reply)

    async def _dispatch(self, cmd: str, args: list[str]) -> str:
        if cmd in ("/start", "/help"):
            return HELP_TEXT
        if cmd == "/health":
            return collect_vps_health().format_message()
        if cmd == "/status":
            status = collect_trading_bot_status(
                self.service_name,
                heartbeat_path=self.heartbeat_path,
            )
            return status.format_message()
        if cmd == "/test":
            ok = await self.notifier.send_test()
            return "✅ Test notification sent." if ok else "❌ Test notification failed."
        if cmd == "/bot_start":
            return ServiceControl(self.service_name).run("start").format_message()
        if cmd == "/bot_stop":
            return ServiceControl(self.service_name).run("stop").format_message()
        if cmd == "/bot_restart":
            return ServiceControl(self.service_name).run("restart").format_message()
        if cmd == "/bot_reload":
            return ServiceControl(self.service_name).run("reload").format_message()
        return f"Unknown command: {cmd}\nSend /help"

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
from notifier.trade_status import format_trade_report, load_trade_report
from notifier.heartbeat import resolve_data_path

logger = logging.getLogger(__name__)

HELP_TEXT = """🤖 Futures Trading Bot — Control

/health — VPS CPU, memory, disk
/status — trading bot systemd + heartbeat
/trade_status — ringkasan trade (waktu, pair, PnL)
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


def normalize_chat_id(chat_id: Any) -> str:
    """Telegram JSON may send chat id as int (e.g. negative for groups)."""
    return str(chat_id).strip()


class TelegramControlBot:
    """Long-polling Telegram bot for ops commands."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        service_name: str,
        heartbeat_path: str,
        db_path: str = "storage/trade_history.db",
        trade_status_limit: int = 10,
        poll_seconds: float = 30.0,
        allowed_user_ids: set[str] | None = None,
    ) -> None:
        self.token = (token or "").strip()
        self.chat_id = normalize_chat_id(chat_id)
        self.service_name = service_name
        self.heartbeat_path = str(resolve_data_path(heartbeat_path))
        self.db_path = str(resolve_data_path(db_path))
        self.trade_status_limit = max(1, min(int(trade_status_limit), 50))
        self.poll_seconds = poll_seconds
        self.allowed_user_ids = allowed_user_ids or set()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.notifier = TelegramNotifier(self.token, self.chat_id)
        self._offset = 0
        self._running = False

    def is_authorized(self, message: dict[str, Any]) -> bool:
        chat = message.get("chat") or {}
        incoming = normalize_chat_id(chat.get("id", ""))
        if incoming != self.chat_id:
            return False
        if not self.allowed_user_ids:
            return True
        user = message.get("from") or {}
        return normalize_chat_id(user.get("id", "")) in self.allowed_user_ids

    async def setup(self) -> bool:
        """Delete webhook (required for polling), verify token, send startup ping."""
        if not self.notifier.is_configured:
            logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty")
            return False

        webhook = await self.notifier.api_call(
            "deleteWebhook",
            {"drop_pending_updates": True},
        )
        if not webhook.get("ok"):
            logger.warning("deleteWebhook: %s", webhook.get("description"))

        me = await self.notifier.api_call("getMe")
        if not me.get("ok"):
            logger.error("Invalid bot token: %s", me.get("description"))
            return False
        username = (me.get("result") or {}).get("username", "?")
        logger.info("Telegram bot @%s — polling chat_id=%s", username, self.chat_id)

        ok = await self.notifier.send_message(
            "🟢 Telegram control bot online.\n"
            f"Chat ID: {self.chat_id}\n"
            "Kirim /help untuk perintah."
        )
        if not ok:
            logger.error(
                "Startup message failed — check TELEGRAM_CHAT_ID=%s "
                "(kirim /start ke bot di chat yang sama, lalu cek ID)",
                self.chat_id,
            )
        return ok

    async def run(self) -> None:
        self._running = True
        logger.info(
            "Telegram control bot started (service=%s, chat=%s)",
            self.service_name,
            self.chat_id,
        )
        if not await self.setup():
            logger.error("Setup failed — commands may not work until config is fixed.")

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
        timeout_sec = aiohttp.ClientTimeout(total=timeout + 15)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/getUpdates",
                params=params,
                timeout=timeout_sec,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("getUpdates HTTP %s: %s", resp.status, text)
                    await asyncio.sleep(5)
                    return []
                data = await resp.json()
        if not data.get("ok"):
            desc = data.get("description", data)
            logger.error("getUpdates not ok: %s", desc)
            if "Conflict" in str(desc) or "terminated by other getUpdates" in str(desc):
                logger.error(
                    "Another process is polling this bot token — "
                    "stop duplicate telegram_bot / webhook apps."
                )
            await asyncio.sleep(5)
            return []
        return data.get("result") or []

    async def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        text = message.get("text") or ""
        if not text.startswith("/"):
            return

        chat = message.get("chat") or {}
        incoming_chat = normalize_chat_id(chat.get("id", ""))
        logger.info("Command received: %s from chat=%s", text.split()[0], incoming_chat)

        if not self.is_authorized(message):
            logger.warning(
                "Unauthorized command (configured chat_id=%s, got=%s)",
                self.chat_id,
                incoming_chat,
            )
            await self.notifier.send_message(
                "⚠️ Chat ini belum terdaftar untuk perintah.\n"
                f"Chat ID Anda: `{incoming_chat}`\n"
                f"TELEGRAM_CHAT_ID saat ini: `{self.chat_id}`\n\n"
                "Set TELEGRAM_CHAT_ID di .env ke Chat ID Anda, lalu:\n"
                "`sudo systemctl restart futures-trading-bot-telegram`",
                chat_id=incoming_chat,
            )
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
        if cmd == "/trade_status":
            limit = self.trade_status_limit
            if args:
                try:
                    limit = max(1, min(int(args[0]), 50))
                except ValueError:
                    return "Usage: /trade_status [limit]\nContoh: /trade_status 15"
            report = await load_trade_report(
                self.db_path,
                heartbeat_path=self.heartbeat_path,
                recent_limit=limit,
            )
            return format_trade_report(report, recent_limit=limit)
        if cmd == "/test":
            ok = await self.notifier.send_test()
            if ok:
                return "✅ Test notification sent (cek pesan 🔔 di atas)."
            return (
                "❌ Gagal kirim notifikasi test.\n"
                "Cek logs/telegram_control.log dan TELEGRAM_CHAT_ID di .env."
            )
        if cmd == "/bot_start":
            return ServiceControl(self.service_name).run("start").format_message()
        if cmd == "/bot_stop":
            return ServiceControl(self.service_name).run("stop").format_message()
        if cmd == "/bot_restart":
            return ServiceControl(self.service_name).run("restart").format_message()
        if cmd == "/bot_reload":
            return ServiceControl(self.service_name).run("reload").format_message()
        return f"Unknown command: {cmd}\nSend /help"

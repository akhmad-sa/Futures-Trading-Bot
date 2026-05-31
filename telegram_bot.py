"""
Telegram control bot entry point — VPS health, bot status, systemd control.

Run separately from the trading engine::

    python telegram_bot.py

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env / configs/exchange.env.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from core.config import load_config
from notifier.control import TelegramControlBot
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


def _parse_allowed_ids(raw: list[str]) -> set[str]:
    ids: set[str] = set()
    for item in raw:
        for part in str(item).split(","):
            part = part.strip()
            if part:
                ids.add(part)
    return ids


async def _main() -> None:
    config = load_config()
    setup_logging(config.log_level, log_file="logs/telegram_control.log")

    if not config.telegram_bot_token or not config.telegram_chat_id:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (see .env.example)."
        )

    bot = TelegramControlBot(
        config.telegram_bot_token,
        config.telegram_chat_id,
        service_name=config.trading_bot_service,
        heartbeat_path=config.heartbeat_path,
        poll_seconds=config.telegram_control_poll_seconds,
        allowed_user_ids=_parse_allowed_ids(config.telegram_allowed_user_ids),
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        bot.stop()
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass

    runner = asyncio.create_task(bot.run())
    await stop_event.wait()
    runner.cancel()
    try:
        await runner
    except asyncio.CancelledError:
        pass
    logger.info("Telegram control bot stopped.")


if __name__ == "__main__":
    asyncio.run(_main())

"""
Telegram control bot entry point — VPS health, bot status, systemd control.

Run separately from the trading engine::

    python telegram_bot.py
    python telegram_bot.py --probe   # one-shot: test token, chat_id, send ping

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env / configs/exchange.env.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

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


async def _probe() -> int:
    config = load_config()
    setup_logging(config.log_level, log_file="logs/telegram_control.log")

    if not config.telegram_bot_token or not config.telegram_chat_id:
        print("FAIL: TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID harus di-set di .env")
        return 1

    bot = TelegramControlBot(
        config.telegram_bot_token,
        config.telegram_chat_id,
        service_name=config.trading_bot_service,
        heartbeat_path=config.heartbeat_path,
        allowed_user_ids=_parse_allowed_ids(config.telegram_allowed_user_id_list()),
    )
    ok = await bot.setup()
    if ok:
        ok = await bot.notifier.send_test()
    print(f"chat_id={config.telegram_chat_id!r} setup_ok={ok}")
    return 0 if ok else 1


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
        allowed_user_ids=_parse_allowed_ids(config.telegram_allowed_user_id_list()),
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
    parser = argparse.ArgumentParser(description="Telegram control bot")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Test token/chat_id and send one message, then exit",
    )
    args, _rest = parser.parse_known_args()
    if args.probe:
        sys.exit(asyncio.run(_probe()))
    asyncio.run(_main())

"""
Entry point for the MEXC futures trading bot.
"""

import asyncio
from core.config import load_config
from core.logger import setup_logging  # will be created in utils
from strategy.example import ExampleStrategy
from exchange.mexc import MEXCExchange
from execution.engine import ExecutionEngine
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier


async def main() -> None:
    """Initialize all components and start the bot."""
    config = load_config()
    setup_logging(config.log_level)

    db = TradeDatabase(config.db_path)
    await db.open()

    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)

    risk_manager = RiskManager(config)
    exchange = MEXCExchange(config)
    await exchange.connect()

    strategy = ExampleStrategy(config)
    engine = ExecutionEngine(exchange, risk_manager, db, notifier)

    await engine.start(strategy)


if __name__ == "__main__":
    asyncio.run(main())

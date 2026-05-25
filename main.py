"""
Entry point for the trading bot.
Supports multiple exchanges via the exchange factory.
"""

import asyncio
from core.config import load_config
from utils.logger import setup_logging
from strategy.registry import StrategyRegistry
from exchange.exchange_factory import create_exchange
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

    # Build exchange configuration dict using the selected exchange's env vars
    exchange_name = config.exchange_name
    exchange_cfg = {
        "api_key": getattr(config, f"{exchange_name}_api_key", ""),
        "api_secret": getattr(config, f"{exchange_name}_api_secret", ""),
    }
    exchange = create_exchange(exchange_name, exchange_cfg)
    await exchange.connect()

    # Load strategies dynamically from config
    registry = StrategyRegistry()
    strategies = registry.load_from_config(config)

    engine = ExecutionEngine(
        exchange,
        risk_manager,
        db,
        notifier,
        symbols=config.symbols,
    )

    await engine.start(strategies)


if __name__ == "__main__":
    asyncio.run(main())

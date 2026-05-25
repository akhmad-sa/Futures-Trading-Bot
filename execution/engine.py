"""
Main execution engine that links exchange, strategy, risk and storage.
"""

import asyncio
import logging
from typing import Any

from exchange.base import BaseExchange
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from strategy.base import BaseStrategy
from execution.trade_executor import TradeExecutor
from execution.position_manager import PositionManager

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Orchestrates the trading lifecycle."""

    def __init__(
        self,
        exchange: BaseExchange,
        risk_manager: RiskManager,
        db: TradeDatabase,
        notifier: TelegramNotifier,
        symbols: list[str] | None = None,
    ) -> None:
        self.exchange = exchange
        self.risk_mgr = risk_manager
        self.db = db
        self.notifier = notifier
        self.symbols = symbols or ["BTCUSDT"]
        self.strategy: BaseStrategy | None = None
        self._running = False
        self._pos_mgr = PositionManager()
        self._trade_executor = TradeExecutor(
            exchange, risk_manager, self._pos_mgr, db, notifier
        )

    async def start(self, strategy: BaseStrategy) -> None:
        """Main loop: fetch data, get signals, execute trades."""
        self.strategy = strategy
        self._running = True

        while self._running:
            try:
                for symbol in self.symbols:
                    ohlcv = await self.exchange.fetch_ohlcv(symbol, limit=100)
                    if not ohlcv:
                        continue

                    signal = await self.strategy.get_signal(symbol, ohlcv)

                    if signal in ("long", "short"):
                        capital = 1000.0  # TODO: fetch actual balance
                        price = ohlcv[-1][4]
                        await self._trade_executor.open_position(
                            symbol, signal, price, capital
                        )
                    elif signal == "close":
                        await self._trade_executor.close_position(symbol)

            except Exception as exc:
                logger.exception("Engine loop error")
                await self.notifier.send_error(str(exc)[:200])

            await asyncio.sleep(5)  # loop period

    async def stop(self) -> None:
        """Gracefully stop the engine."""
        self._running = False

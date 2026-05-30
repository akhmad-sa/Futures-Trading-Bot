"""
Main execution engine that links exchange, strategy, risk and storage.
"""

import asyncio
import logging
from typing import Any, List, Optional, Union

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
        self.strategies: list[BaseStrategy] = []
        self._running = False
        self._pos_mgr = PositionManager()
        self._trade_executor = TradeExecutor(
            exchange, risk_manager, self._pos_mgr, db, notifier
        )

    async def start(
        self, strategies: Union[BaseStrategy, List[BaseStrategy]]
    ) -> None:
        """Main loop: fetch data, get signals, execute trades."""
        if isinstance(strategies, BaseStrategy):
            self.strategies = [strategies]
        else:
            self.strategies = strategies

        self._running = True

        while self._running:
            try:
                for symbol in self.symbols:
                    ohlcv = await self.exchange.fetch_ohlcv(symbol, limit=100)
                    if not ohlcv:
                        continue

                    for strategy in self.strategies:
                        if not strategy.enabled or symbol not in strategy.symbols:
                            continue

                        signal = await strategy.get_signal(symbol, ohlcv)

                        pos = self._pos_mgr.get_position(symbol)
                        if signal == "close":
                            if pos is not None:
                                await self._trade_executor.close_position(symbol)
                                strategy.on_position_closed(
                                    getattr(strategy, "last_exit_reason", "signal")
                                )
                        elif signal in ("long", "short"):
                            if pos is not None and pos["side"] != signal:
                                await self._trade_executor.close_position(symbol)
                            if self._pos_mgr.get_position(symbol) is None:
                                balance = await self.exchange.fetch_balance()
                                capital = float(
                                    balance.get("total", {}).get("USDT", 1000.0)
                                    if isinstance(balance.get("total"), dict)
                                    else 1000.0
                                )
                                price = ohlcv[-1][4]
                                hints = getattr(strategy, "last_entry_hints", None)
                                await self._trade_executor.open_position(
                                    symbol, signal, price, capital, hints=hints
                                )
                                strategy.on_position_opened(signal, price)

            except Exception as exc:
                logger.exception("Engine loop error")
                await self.notifier.send_error(str(exc)[:200])

            await asyncio.sleep(5)  # loop period

    async def stop(self) -> None:
        """Gracefully stop the engine."""
        self._running = False

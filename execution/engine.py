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

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Orchestrates the trading lifecycle."""

    def __init__(
        self,
        exchange: BaseExchange,
        risk_manager: RiskManager,
        db: TradeDatabase,
        notifier: TelegramNotifier,
    ) -> None:
        self.exchange = exchange
        self.risk_mgr = risk_manager
        self.db = db
        self.notifier = notifier
        self.strategy: BaseStrategy | None = None
        self._running = False

    async def start(self, strategy: BaseStrategy) -> None:
        """Main loop: fetch data, get signals, execute trades."""
        self.strategy = strategy
        self._running = True

        symbols = ["BTCUSDT"]  # should be from config

        while self._running:
            try:
                for symbol in symbols:
                    ohlcv = await self.exchange.fetch_ohlcv(symbol, limit=100)

                    signal = await self.strategy.get_signal(symbol, ohlcv)

                    if signal in ("long", "short"):
                        await self._open_position(symbol, signal, ohlcv)
                    elif signal == "close":
                        await self._close_position(symbol)

            except Exception as exc:
                logger.exception("Engine loop error")
                await self.notifier.send_error(str(exc)[:200])

            await asyncio.sleep(5)  # loop period

    async def _open_position(self, symbol: str, side: str, ohlcv: list) -> None:
        """Place a market order and record the trade."""
        if not self.risk_mgr.can_open_position(symbol, side, ohlcv[-1][4]):
            return

        # Simplified: use a fixed capital (better: fetch account balance)
        capital = 1000.0  # placeholder
        price = ohlcv[-1][4]
        size = self.risk_mgr.calculate_position_size(capital, price)

        try:
            order = await self.exchange.create_order(
                symbol, side, size, order_type="market"
            )
            self.risk_mgr.active_positions[symbol] = {
                "side": side,
                "entry_price": price,
                "size": size,
            }
            await self.notifier.send_entry(symbol, side, size, price)
            logger.info("Opened %s %s size=%.4f @ %.2f", side, symbol, size, price)
        except Exception as exc:
            logger.error("Order failed for %s: %s", symbol, exc)
            await self.notifier.send_error(f"Order failed: {symbol} {exc}")

    async def _close_position(self, symbol: str) -> None:
        """Close an existing position."""
        pos = self.risk_mgr.active_positions.pop(symbol, None)
        if pos is None:
            return

        side = "sell" if pos["side"] == "long" else "buy"
        try:
            order = await self.exchange.create_order(
                symbol, side, pos["size"], order_type="market"
            )
            exit_price = order.get("price") or 0.0
            pnl = (exit_price - pos["entry_price"]) * pos["size"]
            if pos["side"] == "short":
                pnl = -pnl

            await self.db.save_trade({
                "symbol": symbol,
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "exit_price": exit_price,
                "quantity": pos["size"],
                "entry_time": "",
                "exit_time": "",
                "pnl": pnl,
            })
            await self.notifier.send_exit(symbol, pos["side"], pnl)
            logger.info("Closed %s PnL=%.2f", symbol, pnl)
        except Exception as exc:
            logger.error("Close order failed for %s: %s", symbol, exc)

    async def stop(self) -> None:
        """Gracefully stop the engine."""
        self._running = False

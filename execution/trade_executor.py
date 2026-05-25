"""
Handles order placement and trade lifecycle.
"""

import logging
from typing import Any

from exchange.base import BaseExchange
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from execution.position_manager import PositionManager

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Executes trades and manages order submission."""

    def __init__(
        self,
        exchange: BaseExchange,
        risk_manager: RiskManager,
        position_manager: PositionManager,
        db: TradeDatabase,
        notifier: TelegramNotifier,
    ) -> None:
        self.exchange = exchange
        self.risk_mgr = risk_manager
        self.pos_mgr = position_manager
        self.db = db
        self.notifier = notifier

    async def open_position(self, symbol: str, side: str, price: float, capital: float) -> None:
        """Open a new position if risk allows."""
        if not self.risk_mgr.can_open_position(
            symbol,
            side,
            price,
            current_positions_count=self.pos_mgr.positions_count,
        ):
            return

        size = self.risk_mgr.calculate_position_size(capital, price)
        try:
            order = await self.exchange.create_order(
                symbol, side, size, order_type="market"
            )
            entry_data = {
                "side": side,
                "entry_price": price,
                "size": size,
            }
            self.pos_mgr.add_position(symbol, entry_data)
            await self.notifier.send_entry(symbol, side, size, price)
            logger.info("Opened %s %s size=%.4f @ %.2f", side, symbol, size, price)
        except Exception as exc:
            logger.error("Order failed for %s: %s", symbol, exc)
            await self.notifier.send_error(f"Order failed: {symbol} {exc}")

    async def close_position(self, symbol: str) -> None:
        """Close an existing open position."""
        pos = self.pos_mgr.remove_position(symbol)
        if pos is None:
            logger.warning("No open position for %s", symbol)
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

            await self.db.save_trade(
                {
                    "symbol": symbol,
                    "side": pos["side"],
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "quantity": pos["size"],
                    "entry_time": "",
                    "exit_time": "",
                    "pnl": pnl,
                }
            )
            await self.notifier.send_exit(symbol, pos["side"], pnl)
            self.risk_mgr.update_daily_loss(pnl)
            logger.info("Closed %s PnL=%.2f", symbol, pnl)
        except Exception as exc:
            logger.error("Close order failed for %s: %s", symbol, exc)
            await self.notifier.send_error(f"Close failed: {symbol} {exc}")

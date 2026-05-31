"""
Handles order placement and trade lifecycle (live / paper).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from exchange.base import BaseExchange
from exchange.models import OrderSide, OrderType
from market_data.models.candle import Candle
from risk.exit_levels import EntryRiskHints, PositionExitState, take_profit_r_multiple
from risk.manager import RiskManager
from risk.partial_profit_log import format_partial_profit_message
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from execution.position_manager import PositionManager
from utils import console as term

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

    async def fetch_equity(self) -> float:
        """Return USDT equity for sizing (total balance)."""
        balance = await self.exchange.fetch_balance()
        return float(balance.total or 0.0)

    async def open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        capital: float,
        hints: Optional[EntryRiskHints] = None,
        bar_index: int = 0,
        *,
        candle_time: Optional[datetime] = None,
        current_positions_count: int = 0,
        sizing_slots: int = 1,
    ) -> bool:
        """Open a new position if risk allows. Returns True when filled."""
        candle_time = candle_time or datetime.now(timezone.utc)
        if not self.risk_mgr.can_open_position(
            symbol,
            side,
            price,
            current_positions_count=current_positions_count,
            current_capital=capital,
        ):
            term.execution_rejected("risk_blocked", candle_time)
            return False

        exit_state = self.risk_mgr.create_exit_state(
            side, price, hints=hints, entry_bar_index=bar_index
        )
        if exit_state is None:
            term.execution_rejected("invalid_stop_loss", candle_time)
            return False

        slots = max(int(sizing_slots), 1)
        sizing_capital = self.risk_mgr.get_sizing_capital(capital) / slots
        size, _ = self.risk_mgr.calculate_position_size(
            sizing_capital, price, stop_loss=exit_state.stop_loss
        )
        if size <= 0:
            term.execution_rejected("zero_quantity", candle_time)
            return False

        order_side = OrderSide.BUY if side == "long" else OrderSide.SELL
        try:
            await self.exchange.create_order(
                symbol, order_side, size, OrderType.MARKET, price=price
            )
            self.pos_mgr.add_position(
                symbol,
                {
                    "side": side,
                    "entry_price": price,
                    "size": size,
                    "exit_state": exit_state,
                    "entry_bar_index": bar_index,
                    "entry_time": candle_time.isoformat(),
                },
            )
            await self.notifier.send_entry(symbol, side, size, price)
            logger.info(
                "Opened %s %s size=%.4f @ %.2f SL=%.2f TP=%.2f",
                side,
                symbol,
                size,
                price,
                exit_state.stop_loss,
                exit_state.take_profit,
            )
            term.execution_open(
                side,
                price,
                size,
                fee=0.0,
                balance=capital,
                candle_time=candle_time,
                symbol=symbol,
            )
            tp_r = take_profit_r_multiple(exit_state)
            term.execution_levels(
                side,
                price,
                exit_state.stop_loss,
                exit_state.take_profit,
                candle_time,
                tp_r=tp_r,
            )
            return True
        except Exception as exc:
            logger.error("Order failed for %s: %s", symbol, exc)
            await self.notifier.send_error(f"Order failed: {symbol} {exc}")
            term.execution_rejected(f"order_failed:{exc}", candle_time)
            return False

    async def partial_close_position(
        self,
        symbol: str,
        fraction: float,
        close_price: float,
        *,
        candle_time: Optional[datetime] = None,
    ) -> bool:
        """Close a fraction of an open position (partial profit)."""
        pos = self.pos_mgr.get_position(symbol)
        if pos is None:
            return False

        candle_time = candle_time or datetime.now(timezone.utc)
        close_qty = pos["size"] * min(max(fraction, 0.0), 1.0)
        if close_qty <= 0:
            return False

        order_side = OrderSide.SELL if pos["side"] == "long" else OrderSide.BUY
        try:
            order = await self.exchange.create_order(
                symbol,
                order_side,
                close_qty,
                OrderType.MARKET,
                price=close_price,
            )
            exec_price = float(order.price or close_price or pos["entry_price"])
        except Exception as exc:
            logger.error("Partial close failed for %s: %s", symbol, exc)
            return False

        if pos["side"] == "long":
            gross_pnl = (exec_price - pos["entry_price"]) * close_qty
        else:
            gross_pnl = (pos["entry_price"] - exec_price) * close_qty

        self.risk_mgr.record_trade_pnl(gross_pnl)
        if hasattr(self.exchange, "apply_pnl"):
            self.exchange.apply_pnl(gross_pnl)
        pos["size"] -= close_qty
        exit_state: PositionExitState = pos["exit_state"]
        exit_state = self.risk_mgr.mark_partial_profit_taken(exit_state)
        pos["exit_state"] = exit_state

        trigger_r = float(getattr(self.risk_mgr.config, "partial_profit_at_r", 1.0))
        term.partial_profit(
            pos["side"],
            fraction * 100.0,
            exec_price,
            gross_pnl,
            pos["size"],
            candle_time,
            symbol=symbol,
            entry=pos["entry_price"],
            sl_breakeven=exit_state.stop_loss,
            tp_runner=exit_state.take_profit,
            tp_r=take_profit_r_multiple(exit_state),
            trigger_r=trigger_r,
        )
        logger.info(
            format_partial_profit_message(
                symbol=symbol,
                state=exit_state,
                exec_price=exec_price,
                close_pct=fraction * 100.0,
                close_qty=close_qty,
                total_qty_before=pos["size"] + close_qty,
                net_pnl=gross_pnl,
                commission=0.0,
                remaining_qty=pos["size"],
                trigger_r=trigger_r,
            )
        )
        return True

    async def close_position(
        self,
        symbol: str,
        *,
        close_price: Optional[float] = None,
        reason: str = "signal",
        candle_time: Optional[datetime] = None,
    ) -> None:
        """Close the remaining open position."""
        pos = self.pos_mgr.get_position(symbol)
        if pos is None:
            logger.warning("No open position for %s", symbol)
            return

        candle_time = candle_time or datetime.now(timezone.utc)
        order_side = OrderSide.SELL if pos["side"] == "long" else OrderSide.BUY
        try:
            order = await self.exchange.create_order(
                symbol,
                order_side,
                pos["size"],
                OrderType.MARKET,
                price=close_price,
            )
            exit_price = float(
                order.price or close_price or pos["entry_price"]
            )
        except Exception as exc:
            logger.error("Close order failed for %s: %s", symbol, exc)
            await self.notifier.send_error(f"Close failed: {symbol} {exc}")
            return

        if pos["side"] == "long":
            pnl = (exit_price - pos["entry_price"]) * pos["size"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["size"]

        self.pos_mgr.remove_position(symbol)
        self.risk_mgr.record_trade_pnl(pnl)
        if hasattr(self.exchange, "apply_pnl"):
            self.exchange.apply_pnl(pnl)

        await self.db.save_trade(
            {
                "symbol": symbol,
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "exit_price": exit_price,
                "quantity": pos["size"],
                "entry_time": pos.get("entry_time", ""),
                "exit_time": candle_time.isoformat(),
                "pnl": pnl,
            }
        )
        await self.notifier.send_exit(symbol, pos["side"], pnl)
        equity = await self.fetch_equity()
        term.exit_trade(
            pos["side"],
            reason,
            exit_price,
            pnl,
            commission=0.0,
            balance=equity,
            candle_time=candle_time,
        )
        logger.info("Closed %s %s PnL=%.2f reason=%s", symbol, pos["side"], pnl, reason)

    async def process_risk_exits(
        self,
        symbol: str,
        close: float,
        bar_index: int,
        strategy: Any,
        *,
        candle_time: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Update milestones, optional partial profit, then SL/TP check.
        Returns exit reason if the position was closed.
        """
        pos = self.pos_mgr.get_position(symbol)
        if pos is None:
            return None

        candle_time = candle_time or datetime.now(timezone.utc)
        exit_state: PositionExitState = pos["exit_state"]
        exit_state, _ = self.risk_mgr.update_exit_milestones(
            exit_state, close, symbol=symbol
        )
        pos["exit_state"] = exit_state

        partial_frac = self.risk_mgr.partial_profit_size_pct(exit_state, close)
        if partial_frac is not None and partial_frac > 0:
            await self.partial_close_position(
                symbol, partial_frac, close, candle_time=candle_time
            )
            pos = self.pos_mgr.get_position(symbol)
            if pos is None:
                return "partial_profit"

        if pos is not None:
            exit_state = pos["exit_state"]
            reason = self.risk_mgr.check_position_exit(
                exit_state, close, bar_index
            )
            if reason:
                await self.close_position(
                    symbol,
                    close_price=close,
                    reason=reason,
                    candle_time=candle_time,
                )
                strategy.on_position_closed(
                    reason, candle_index=bar_index
                )
                return reason
        return None

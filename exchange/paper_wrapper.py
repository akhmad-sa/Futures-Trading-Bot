"""
Simulated execution wrapper for paper trading.

MEXC (and some other adapters) do not expose ccxt sandbox URLs. Paper mode uses
live market data but simulates fills and tracks a virtual USDT balance.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from exchange.base import BaseExchange
from exchange.models import (
    Balance,
    Candle,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
)

logger = logging.getLogger(__name__)


class PaperTradingExchange(BaseExchange):
    """Delegates market data to a real exchange; simulates orders and balance."""

    exchange_name = "paper"

    def __init__(self, inner: BaseExchange, *, initial_balance: float = 10_000.0) -> None:
        self.config = inner.config
        self._inner = inner
        self.exchange = getattr(inner, "exchange", None)
        self._cash = float(initial_balance)
        self._last_prices: dict[str, float] = {}
        self._order_seq = 0

    async def connect(self) -> None:
        await self._inner.connect()
        logger.info(
            "[PAPER] Simulated trading enabled (initial balance=%.2f USDT). "
            "Market data from %s; no real orders.",
            self._cash,
            getattr(self._inner, "exchange_name", "exchange"),
        )

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", limit: int = 100
    ) -> List[Candle]:
        candles = await self._inner.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if candles:
            self._last_prices[symbol] = float(candles[-1].close)
        return candles

    def apply_pnl(self, pnl: float) -> None:
        """Update virtual balance after a simulated close or partial."""
        self._cash += float(pnl)

    def _fill_price(
        self, symbol: str, price: Optional[float]
    ) -> float:
        if price is not None and price > 0:
            return float(price)
        mark = self._last_prices.get(symbol)
        if mark is None or mark <= 0:
            raise ValueError(f"No price available to simulate fill for {symbol}")
        return mark

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        order_type: OrderType,
        price: Optional[float] = None,
    ) -> Order:
        fill = self._fill_price(symbol, price)
        self._last_prices[symbol] = fill
        self._order_seq += 1
        order_id = f"paper-{self._order_seq}-{uuid.uuid4().hex[:8]}"
        logger.info(
            "[PAPER] Simulated %s %s %s qty=%.6f @ %.4f",
            order_type.value,
            side.value,
            symbol,
            amount,
            fill,
        )
        return Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            status=OrderStatus.CLOSED,
            price=fill,
            amount=amount,
            filled=amount,
            remaining=0.0,
            cost=fill * amount,
            timestamp=datetime.now(timezone.utc),
            exchange=self.exchange_name,
            info={"simulated": True},
        )

    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        return Order(
            id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.CANCELED,
            price=0.0,
            amount=0.0,
            filled=0.0,
            remaining=0.0,
            cost=0.0,
            timestamp=datetime.now(timezone.utc),
            exchange=self.exchange_name,
        )

    async def fetch_position(self, symbol: str) -> Position:
        return await self._inner.fetch_position(symbol)

    async def fetch_balance(self) -> Balance:
        return Balance(
            total=self._cash,
            free=self._cash,
            used=0.0,
            currency="USDT",
            exchange=self.exchange_name,
        )

    async def on_websocket_message(self, message: dict) -> None:
        await self._inner.on_websocket_message(message)

    async def subscribe_ticker(self, symbol: str, callback: Callable) -> None:
        await self._inner.subscribe_ticker(symbol, callback)

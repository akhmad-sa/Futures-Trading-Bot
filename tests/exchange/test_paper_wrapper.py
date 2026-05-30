"""Tests for paper trading wrapper."""

import pytest

from exchange.models import OrderSide, OrderType
from exchange.paper_wrapper import PaperTradingExchange


class _StubExchange:
    exchange_name = "stub"
    config = {}

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def fetch_ohlcv(self, symbol, timeframe="1m", limit=100):
        from exchange.models import Candle

        return [
            Candle(
                timestamp=1,
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=1,
            )
        ]

    async def fetch_position(self, symbol):
        raise NotImplementedError

    async def on_websocket_message(self, message):
        return None

    async def subscribe_ticker(self, symbol, callback):
        return None


@pytest.mark.asyncio
async def test_simulated_order_uses_last_close():
    paper = PaperTradingExchange(_StubExchange(), initial_balance=250.0)
    await paper.fetch_ohlcv("TRBUSDT")
    order = await paper.create_order(
        "TRBUSDT", OrderSide.BUY, 1.0, OrderType.MARKET, price=None
    )
    assert order.price == 100.5
    assert order.filled == 1.0


def test_apply_pnl_updates_balance():
    paper = PaperTradingExchange(_StubExchange(), initial_balance=250.0)
    paper.apply_pnl(10.0)
    assert paper._cash == 260.0

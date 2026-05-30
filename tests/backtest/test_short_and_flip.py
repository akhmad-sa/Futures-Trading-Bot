"""
Backtest engine tests for short entries and position flips.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backtest.engine import BacktestEngine, RiskConfig as BacktestRiskConfig
from market_data import MarketDataService
from market_data.models.candle import Candle
from risk.manager import RiskManager, RiskConfig
from simulation.config import SimulationConfig


def _candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            timestamp=1_700_000_000_000 + i * 3_600_000,
            open=c,
            high=c * 1.001,
            low=c * 0.999,
            close=c,
            volume=100.0,
        )
        for i, c in enumerate(closes)
    ]


class TestBacktestShortAndFlip:
    @pytest.mark.asyncio
    async def test_opens_short_position(self):
        strategy = MagicMock()
        strategy.get_signal = AsyncMock(
            side_effect=lambda _s, cs: "short" if len(cs) == 2 else "hold"
        )

        service = MarketDataService(provider=_candles([100.0, 99.0, 98.0]))
        risk_manager = RiskManager(RiskConfig())
        risk_manager.reset_all(initial_capital=10_000.0)

        engine = BacktestEngine(
            risk_manager=risk_manager,
            initial_capital=10_000.0,
            simulation_config=SimulationConfig(
                maker_fee=0.0, taker_fee=0.0, slippage_bps=0,
            ),
        )

        report = await engine.run(
            service=service,
            strategy=strategy,
            symbol="BTCUSDT",
            timeframe="1h",
        )

        # Force-closed short at end of replay
        assert len(report.trades) == 1
        assert report.trades[0].side == "short"

    @pytest.mark.asyncio
    async def test_flips_long_to_short(self):
        strategy = MagicMock()

        async def get_signal(_symbol, candles):
            n = len(candles)
            if n == 1:
                return "long"
            if n == 3:
                return "short"
            if n == 5:
                return "close"
            return "hold"

        strategy.get_signal = AsyncMock(side_effect=get_signal)

        service = MarketDataService(
            provider=_candles([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        )
        risk_manager = RiskManager(RiskConfig())
        risk_manager.reset_all(initial_capital=10_000.0)

        engine = BacktestEngine(
            risk_manager=risk_manager,
            initial_capital=10_000.0,
            risk_config=BacktestRiskConfig(max_leverage=10.0),
            simulation_config=SimulationConfig(
                maker_fee=0.0, taker_fee=0.0, slippage_bps=0,
            ),
        )

        report = await engine.run(
            service=service,
            strategy=strategy,
            symbol="BTCUSDT",
            timeframe="1h",
        )

        assert len(report.trades) == 2
        assert report.trades[0].side == "long"
        assert report.trades[1].side == "short"

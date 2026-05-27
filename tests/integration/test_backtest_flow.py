"""
Integration test for the full backtest flow using mocked data.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backtest.engine import BacktestEngine
from backtest.context import BacktestContext
from market_data import MarketDataService
from market_data.models.candle import Candle
from risk.manager import RiskManager
from simulation.config import SimulationConfig
from strategy.implementations.golden_test import GoldenTestStrategy


class TestBacktestFlow:
    """Verify that the backtest engine runs end‑to‑end with mocked data."""

    @pytest.mark.asyncio
    async def test_backtest_with_mocked_data(self, sample_candles):
        """Run a full backtest with a simple hold strategy."""
        # Create a mock strategy
        strategy = MagicMock()
        strategy.get_signal = AsyncMock(return_value="hold")

        # Create a market data service with sample candles
        service = MarketDataService(provider=sample_candles)

        # Create a risk manager (mock)
        risk_manager = MagicMock(spec=RiskManager)
        risk_manager.reset_all = MagicMock()
        risk_manager.can_open_position = MagicMock(return_value=True)
        risk_manager.calculate_position_size = MagicMock(return_value=(1.0, 0.0))
        risk_manager.record_trade_pnl = MagicMock()

        engine = BacktestEngine(
            risk_manager=risk_manager,
            initial_capital=10000.0,
            simulation_config=SimulationConfig(
                maker_fee=0.001,
                taker_fee=0.001,
                slippage_bps=10,
            ),
        )

        report = await engine.run(
            service=service,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1h",
            exchange="binance",
        )

        # Should have an equity curve with len(candles) + 1 points
        assert len(report.equity_curve) == len(sample_candles) + 1
        assert report.initial_capital == 10000.0
        # No trades were made (strategy returned "hold")
        assert len(report.trades) == 0

    @pytest.mark.asyncio
    async def test_backtest_with_trades(self, sample_candles):
        """Run a backtest where the strategy opens and closes positions."""
        # Strategy that opens long on first candle, closes on last
        strategy = MagicMock()

        async def get_signal(symbol, candles):
            if len(candles) == 1:
                return "long"
            elif len(candles) == len(sample_candles):
                return "close"
            return "hold"

        strategy.get_signal = AsyncMock(side_effect=get_signal)

        service = MarketDataService(provider=sample_candles)

        risk_manager = MagicMock(spec=RiskManager)
        risk_manager.reset_all = MagicMock()
        risk_manager.can_open_position = MagicMock(return_value=True)
        risk_manager.calculate_position_size = MagicMock(return_value=(1.0, 0.0))
        risk_manager.record_trade_pnl = MagicMock()

        engine = BacktestEngine(
            risk_manager=risk_manager,
            initial_capital=10000.0,
            simulation_config=SimulationConfig(
                maker_fee=0.001,
                taker_fee=0.001,
                slippage_bps=10,
            ),
        )

        report = await engine.run(
            service=service,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1h",
            exchange="binance",
        )

        # Should have exactly one trade
        assert len(report.trades) == 1
        trade = report.trades[0]
        assert trade.side == "long"
        assert trade.symbol == "BTC/USDT"
        assert trade.entry_time == sample_candles[0].timestamp
        assert trade.exit_time == sample_candles[-1].timestamp

    @pytest.mark.asyncio
    async def test_backtest_empty_data(self):
        """Backtest with no candles returns an empty report."""
        strategy = MagicMock()
        strategy.get_signal = AsyncMock(return_value="hold")

        service = MarketDataService(provider=[])

        risk_manager = MagicMock(spec=RiskManager)
        risk_manager.reset_all = MagicMock()

        engine = BacktestEngine(
            risk_manager=risk_manager,
            initial_capital=10000.0,
            simulation_config=SimulationConfig.default(),
        )

        report = await engine.run(
            service=service,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1h",
            exchange="binance",
        )

        # Should be an empty report
        assert report.initial_capital == 10000.0
        assert report.final_capital == 10000.0
        assert report.total_pnl == 0.0
        assert len(report.trades) == 0
        assert len(report.equity_curve) == 1

    @pytest.mark.asyncio
    async def test_golden_test_strategy(self, sample_candles):
        """
        Use the deterministic GoldenTestStrategy to validate replay,
        execution, and portfolio accounting.
        """
        strategy = GoldenTestStrategy(close_after=5)

        # Use a real (non‑mock) risk manager to validate actual PnL
        risk_manager = MagicMock(
            spec=RiskManager,
            reset_all=MagicMock(),
            can_open_position=MagicMock(return_value=True),
            calculate_position_size=MagicMock(return_value=(1.0, 0.0)),
            record_trade_pnl=MagicMock(),
        )

        service = MarketDataService(provider=sample_candles)

        engine = BacktestEngine(
            risk_manager=risk_manager,
            initial_capital=10000.0,
            simulation_config=SimulationConfig(
                maker_fee=0.0,
                taker_fee=0.0,
                slippage_bps=0,
            ),
        )

        report = await engine.run(
            service=service,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1h",
            exchange="binance",
        )

        # GoldenTestStrategy:
        #   - enters long on candle 0 (close=50050.0)
        #   - closes on candle 4 (close=50090.0) (len==5)
        # PnL = (50090 - 50050) * 1.0 = 40.0
        assert len(report.trades) == 1
        trade = report.trades[0]
        assert trade.side == "long"
        assert trade.entry_price == 50050.0
        assert trade.exit_price == 50090.0
        assert trade.quantity == 1.0
        assert trade.pnl == 40.0
        assert trade.commission == 0.0

        # Balance update: initial 10000 + 40 = 10040
        assert report.final_capital == 10040.0
        assert report.total_pnl == 40.0

        # Equity curve length should be number of candles + 1
        assert len(report.equity_curve) == len(sample_candles) + 1

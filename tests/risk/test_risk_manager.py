"""
Tests for the risk manager.
"""

from risk.manager import RiskManager, RiskConfig
from risk.exit_levels import EntryRiskHints


class TestRiskManager:
    def test_drawdown_uses_current_capital_not_cumulative_pnl(self):
        rm = RiskManager(RiskConfig(max_drawdown_percent=20.0))
        rm.reset_all(initial_capital=10_000.0)
        assert rm.can_open_position("BTCUSDT", "short", 50_000.0, 0, 9_900.0)
        assert not rm.can_open_position("BTCUSDT", "short", 50_000.0, 0, 7_500.0)

    def test_reset_all_sets_peak_equity(self):
        rm = RiskManager(RiskConfig())
        rm.reset_all(initial_capital=10_000.0)
        assert rm.peak_equity == 10_000.0

    def test_compounding_uses_current_equity(self):
        cfg = RiskConfig(compounding_enabled=True, position_size_pct=1.0)
        rm = RiskManager(cfg)
        rm.reset_all(initial_capital=10_000.0)
        assert rm.get_sizing_capital(12_000.0) == 12_000.0

    def test_fixed_capital_when_compounding_disabled(self):
        cfg = RiskConfig(compounding_enabled=False, position_size_pct=1.0)
        rm = RiskManager(cfg)
        rm.reset_all(initial_capital=10_000.0)
        assert rm.get_sizing_capital(12_000.0) == 10_000.0

    def test_martingale_increases_after_losses(self):
        cfg = RiskConfig(
            martingale_enabled=True,
            martingale_multiplier=2.0,
            martingale_max_steps=3,
        )
        rm = RiskManager(cfg)
        rm.reset_all(initial_capital=10_000.0)
        assert rm.get_martingale_multiplier() == 1.0
        rm.record_trade_pnl(-10.0)
        assert rm.martingale_step == 1
        assert rm.get_martingale_multiplier() == 2.0
        rm.record_trade_pnl(-10.0)
        assert rm.martingale_step == 2
        assert rm.get_martingale_multiplier() == 4.0
        rm.record_trade_pnl(20.0)
        assert rm.martingale_step == 0
        assert rm.get_martingale_multiplier() == 1.0

    def test_create_exit_state_long(self):
        rm = RiskManager(RiskConfig(take_profit_rr=2.0, stop_loss_mode="percent", stop_loss_pct=0.01))
        state = rm.create_exit_state(
            "long",
            100.0,
            hints=EntryRiskHints(stop_anchor=99.0, atr_value=1.0),
            entry_bar_index=5,
        )
        assert state is not None
        assert state.stop_loss < 100.0
        assert state.take_profit > 100.0

    def test_position_size_respects_min_stop_distance(self):
        cfg = RiskConfig(risk_per_trade=0.02, min_sl_pct=0.005, max_leverage=5)
        rm = RiskManager(cfg)
        rm.reset_all(initial_capital=250.0)
        price = 80_000.0
        tight_sl = price - 50.0
        qty, _ = rm.calculate_position_size(250.0, price, stop_loss=tight_sl)
        notional = qty * price
        assert notional <= 250.0 * 5.0 + 1.0
        assert qty <= (250.0 * 5.0) / price + 1e-6

    def test_min_sl_floor_on_exit_state(self):
        from risk.exit_levels import create_exit_state, EntryRiskHints

        state = create_exit_state(
            "long",
            100.0,
            hints=EntryRiskHints(stop_anchor=99.95),
            entry_bar_index=0,
            atr_multiplier=2.0,
            min_sl_pct=0.005,
            max_sl_pct=0.018,
            stop_loss_pct=0.015,
            stop_loss_mode="atr",
            risk_reward=3.0,
        )
        assert state is not None
        assert state.initial_risk >= 0.5

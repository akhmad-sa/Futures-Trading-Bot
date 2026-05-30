from risk.exit_levels import PositionExitState
from risk.partial_profit_log import format_partial_profit_message


def test_format_partial_profit_message():
    state = PositionExitState(
        side="short",
        entry_price=100.0,
        stop_loss=101.0,
        take_profit=0.0,
        initial_risk=1.0,
        reached_1r=True,
    )
    msg = format_partial_profit_message(
        symbol="BTCUSDT",
        state=state,
        exec_price=99.0,
        close_pct=30.0,
        close_qty=0.3,
        total_qty_before=1.0,
        net_pnl=0.28,
        commission=0.02,
        remaining_qty=0.7,
        trigger_r=1.0,
    )
    assert "PARTIAL-PROFIT" in msg
    assert "BTCUSDT" in msg
    assert "breakeven" in msg
    assert "runner" in msg

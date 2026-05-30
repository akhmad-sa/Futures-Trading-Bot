from backtest.metrics import compute_exit_summary
from backtest.models import TradeRecord


def _trade(reason: str, pnl: float) -> TradeRecord:
    return TradeRecord(
        symbol="BTCUSDT",
        side="long",
        entry_time=0,
        exit_time=1,
        entry_price=100.0,
        exit_price=101.0,
        quantity=1.0,
        pnl=pnl,
        commission=0.0,
        close_reason=reason,
    )


def test_compute_exit_summary_groups_by_reason():
    trades = [
        _trade("take_profit", 10.0),
        _trade("take_profit", 5.0),
        _trade("stop_loss", -3.0),
        _trade("trend_exit", -1.0),
        _trade("partial_profit", 4.0),
        _trade("flip", 2.0),
    ]
    summary = compute_exit_summary(trades)
    assert summary.take_profit == 2
    assert summary.stop_loss == 1
    assert summary.trend_exit == 1
    assert summary.partial_profit == 1
    assert summary.other == 1
    assert summary.take_profit_pnl == 15.0
    assert summary.stop_loss_pnl == -3.0
    assert summary.trend_exit_pnl == -1.0
    assert summary.partial_profit_pnl == 4.0
    assert summary.other_pnl == 2.0
    assert summary.total == 6

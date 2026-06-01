from notifier.trade_status import TradeReport, SymbolSummary, format_trade_report


def test_format_trade_report_open_only():
    report = TradeReport(
        recent=[],
        by_symbol=[],
        total_trades=0,
        total_wins=0,
        total_losses=0,
        total_pnl=0.0,
        open_positions=[
            {
                "symbol": "TRBUSDT",
                "side": "long",
                "entry_price": 16.86,
                "size": 1647.75,
                "entry_time": "2026-06-01T00:10:00+00:00",
            }
        ],
    )
    msg = format_trade_report(report)
    assert "Open (1):" in msg
    assert "TRBUSDT" in msg
    assert "belum closed" in msg
    assert "Closed: belum ada" in msg


def test_format_trade_report_with_trades():
    recent = [
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "exit_time": "2025-05-31T14:32:00+00:00",
            "pnl": 12.5,
        },
    ]
    by_symbol = [SymbolSummary("BTCUSDT", 1, 1, 0, 12.5)]
    report = TradeReport(
        recent=recent,
        by_symbol=by_symbol,
        total_trades=1,
        total_wins=1,
        total_losses=0,
        total_pnl=12.5,
    )
    msg = format_trade_report(report, recent_limit=10)
    assert "Closed recent" in msg
    assert "Realised PnL: +12.50" in msg

from notifier.trade_status import TradeReport, SymbolSummary, format_trade_report


def test_format_trade_report_empty():
    report = TradeReport([], [], 0, 0, 0, 0.0)
    msg = format_trade_report(report)
    assert "Belum ada trade" in msg


def test_format_trade_report_with_trades():
    recent = [
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "exit_time": "2025-05-31T14:32:00+00:00",
            "pnl": 12.5,
        },
        {
            "symbol": "ETHUSDT",
            "side": "short",
            "exit_time": "2025-05-30T09:15:00+00:00",
            "pnl": -3.2,
        },
    ]
    by_symbol = [
        SymbolSummary("BTCUSDT", 1, 1, 0, 12.5),
        SymbolSummary("ETHUSDT", 1, 0, 1, -3.2),
    ]
    report = TradeReport(
        recent=recent,
        by_symbol=by_symbol,
        total_trades=2,
        total_wins=1,
        total_losses=1,
        total_pnl=9.3,
    )
    msg = format_trade_report(report, recent_limit=10)
    assert "BTCUSDT" in msg
    assert "ETHUSDT" in msg
    assert "Summary:" in msg
    assert "Total PnL: +9.30" in msg
    assert "By pair:" in msg

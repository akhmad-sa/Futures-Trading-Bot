from notifier.bot_status import TradingBotStatus, _bot_label, _state_label
from notifier.log_summary import format_log_line, summarize_last_activity


def test_format_log_line_execution():
    raw = "[EXECUTION] OPEN TRBUSDT LONG at 16.86, size=1647.7505 | 2026-06-01 00:10:00"
    out = format_log_line(raw)
    assert "OPEN" in out
    assert "TRBUSDT" in out
    assert "00:10" in out


def test_format_log_line_telegram_error():
    raw = (
        "2026-06-01 00:15:25 | ERROR    | notifier.telegram | "
        "Telegram send failed: {\"ok\":false,\"error_code\":404,\"description\":\"Not Found\"}"
    )
    out = format_log_line(raw)
    assert "Error Telegram" in out
    assert "token invalid" in out


def test_format_log_line_systemd_noise():
    raw = "2026-06-01T04:47:47+00:00 vmi3336098 systemd[1]: Stopping futures-trading-bot-paper.service"
    assert format_log_line(raw) == ""


def test_summarize_last_activity_prefers_execution_over_systemd():
    lines = [
        "2026-06-01T04:47:47+00:00 systemd[1]: Started futures-trading-bot-paper.service",
        "[PICK] TRBUSDT LONG score=85 | 2026-06-01 00:10:00",
        "[EXECUTION] OPEN TRBUSDT LONG at 16.86, size=1.0 | 2026-06-01 00:10:00",
    ]
    result = summarize_last_activity(lines)
    assert result is not None
    assert "OPEN" in result
    assert "TRBUSDT" in result


def test_format_message_compact_no_path():
    status = TradingBotStatus(
        service_name="futures-trading-bot-paper",
        active_state="active",
        sub_state="running",
        main_pid="123",
        heartbeat=None,
        heartbeat_age_s=None,
        heartbeat_path="storage/heartbeat.json",
        last_activity="OPEN TRBUSDT LONG at 16.86 · 00:10 UTC",
    )
    msg = status.format_message()
    assert "Bot paper — running" in msg
    assert "/opt/" not in msg
    assert "Sinyal: belum terdeteksi" in msg
    assert "Terakhir: OPEN TRBUSDT" in msg
    assert "PID" not in msg
    assert "Service:" not in msg


def test_format_message_with_heartbeat():
    status = TradingBotStatus(
        service_name="futures-trading-bot-paper",
        active_state="active",
        sub_state="running",
        main_pid="123",
        heartbeat={
            "mode": "papertrade",
            "phase": "running",
            "symbols": ["TRBUSDT", "DOGEUSDT"],
            "open_positions": 1,
            "open_positions_detail": [
                {"symbol": "TRBUSDT", "side": "long", "entry_price": 16.86},
            ],
        },
        heartbeat_age_s=25.0,
        heartbeat_path="storage/heartbeat.json",
        last_activity=None,
    )
    msg = status.format_message()
    assert "Scan: TRBUSDT DOGEUSDT" in msg
    assert "posisi open: 1" in msg
    assert "TRBUSDT LONG @ 16.8600" in msg
    assert "Sinyal: 25s lalu" in msg


def test_bot_label_and_state():
    assert _bot_label("futures-trading-bot-paper") == "paper"
    assert _bot_label("futures-trading-bot-live") == "live"
    assert _state_label("active", "running") == "running"
    assert _state_label("inactive", "dead") == "stopped"

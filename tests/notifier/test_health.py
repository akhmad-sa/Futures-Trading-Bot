from notifier.health import collect_vps_health
from notifier.control import parse_command


def test_collect_vps_health_returns_metrics():
    health = collect_vps_health()
    assert health.hostname
    assert health.cpu_count >= 1
    assert health.mem_total_mb >= 0
    assert health.disk_total_gb >= 0
    msg = health.format_message()
    assert "VPS Health" in msg


def test_parse_command_strips_bot_suffix():
    cmd, args = parse_command("/health@MyBot")
    assert cmd == "/health"
    assert args == []


def test_parse_command_with_args():
    cmd, args = parse_command("/bot_restart now")
    assert cmd == "/bot_restart"
    assert args == ["now"]

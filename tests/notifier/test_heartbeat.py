from pathlib import Path

from notifier.heartbeat import heartbeat_age_seconds, read_heartbeat, write_heartbeat


def test_heartbeat_roundtrip(tmp_path: Path):
    path = tmp_path / "hb.json"
    write_heartbeat(path, {"mode": "papertrade", "open_positions": 0})
    data = read_heartbeat(path)
    assert data is not None
    assert data["mode"] == "papertrade"
    assert "ts" in data
    age = heartbeat_age_seconds(data)
    assert age is not None
    assert age < 5.0

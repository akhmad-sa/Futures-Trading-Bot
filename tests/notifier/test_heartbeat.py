from pathlib import Path

from notifier.heartbeat import heartbeat_age_seconds, read_heartbeat, write_heartbeat


def test_heartbeat_uses_project_root(tmp_path, monkeypatch):
    from core import config_loader

    monkeypatch.setattr(config_loader, "_PROJECT_ROOT", tmp_path)
    from notifier.heartbeat import write_heartbeat, read_heartbeat, resolve_data_path

    path = write_heartbeat("storage/heartbeat.json", {"mode": "papertrade"})
    assert path == tmp_path / "storage" / "heartbeat.json"
    data = read_heartbeat("storage/heartbeat.json")
    assert data is not None
    assert data["mode"] == "papertrade"

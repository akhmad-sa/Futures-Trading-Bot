"""Tests for modular config env file discovery."""

from pathlib import Path

from core.config_loader import config_env_files, configs_dir, project_root
from core.config import load_config


def test_configs_dir_exists():
    assert configs_dir().is_dir()


def test_config_env_files_includes_module_envs():
    files = config_env_files()
    names = {Path(f).name for f in files}
    assert "risk.env" in names
    assert "market_structure.env" in names
    assert "logging.env" in names


def test_config_env_files_order_configs_before_root():
    files = config_env_files()
    if len(files) < 2:
        return
    config_indices = [i for i, f in enumerate(files) if "/configs/" in f.replace("\\", "/")]
    root_indices = [i for i, f in enumerate(files) if f.endswith("/.env") or f.endswith("\\.env")]
    if config_indices and root_indices:
        assert max(config_indices) < min(root_indices)


def test_load_config_reads_module_defaults():
    config = load_config()
    assert config.timeframe  # from market_structure.env
    assert config.risk_per_trade > 0  # from risk.env
    assert config.structure_log_mode in ("off", "events", "full")


def test_telegram_allowed_user_ids_empty():
    from core.config import AppConfig

    cfg = AppConfig(TELEGRAM_ALLOWED_USER_IDS="")
    assert cfg.telegram_allowed_user_id_list() == []


def test_telegram_allowed_user_ids_comma_separated():
    from core.config import AppConfig

    cfg = AppConfig(TELEGRAM_ALLOWED_USER_IDS="111, 222")
    assert cfg.telegram_allowed_user_id_list() == ["111", "222"]


def test_telegram_allowed_user_ids_bare_int():
    from core.config import AppConfig

    cfg = AppConfig(TELEGRAM_ALLOWED_USER_IDS=1921646439)
    assert cfg.telegram_allowed_user_ids == "1921646439"
    assert cfg.telegram_allowed_user_id_list() == ["1921646439"]


def test_resolved_structure_log_mode_legacy_verbose():
    from core.config import AppConfig

    cfg = AppConfig(structure_log_verbose=True, structure_log_mode="off")
    assert cfg.resolved_structure_log_mode() == "full"

    cfg2 = AppConfig(structure_log_verbose=False, structure_log_mode="events")
    assert cfg2.resolved_structure_log_mode() == "events"

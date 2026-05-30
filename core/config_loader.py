"""
Discover and load modular env files from ``configs/``.

Loading order (later overrides earlier):
  1. ``configs/*.env`` (alphabetical)
  2. root ``.env`` (secrets + local overrides)

Environment variables always take highest precedence (pydantic-settings).
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIGS_DIR = _PROJECT_ROOT / "configs"


def project_root() -> Path:
    return _PROJECT_ROOT


def configs_dir() -> Path:
    return _CONFIGS_DIR


def config_env_files() -> tuple[str, ...]:
    """Return env file paths for pydantic-settings ``env_file``."""
    files: list[str] = []
    if _CONFIGS_DIR.is_dir():
        for path in sorted(_CONFIGS_DIR.glob("*.env")):
            files.append(str(path))
    root_env = _PROJECT_ROOT / ".env"
    if root_env.is_file():
        files.append(str(root_env))
    return tuple(files)

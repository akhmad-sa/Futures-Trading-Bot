"""
Trading bot heartbeat file — written by the live engine, read by the control bot.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_heartbeat(path: str | Path, payload: dict[str, Any]) -> None:
    """Atomically write heartbeat JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data.setdefault("ts", datetime.now(timezone.utc).isoformat())
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(target)


def read_heartbeat(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Heartbeat read failed: %s", exc)
        return None


def heartbeat_age_seconds(data: dict[str, Any] | None) -> float | None:
    if not data or "ts" not in data:
        return None
    try:
        ts = datetime.fromisoformat(str(data["ts"]).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except (TypeError, ValueError):
        return None

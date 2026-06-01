"""
Parse logs/trading.log into one-line human summaries for Telegram /status.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.config_loader import project_root

# Priority: lower index = higher priority when scanning newest-first groups
_ACTIVITY_PATTERNS: list[tuple[int, re.Pattern[str]]] = [
    (1, re.compile(r"\[EXECUTION\]\s+OPEN", re.I)),
    (1, re.compile(r"\[EXECUTION\]\s+REJECTED", re.I)),
    (2, re.compile(r"\[PICK\]", re.I)),
    (3, re.compile(r"\|\s*ERROR\s*\|", re.I)),
    (3, re.compile(r"Order failed", re.I)),
    (3, re.compile(r"Close order failed", re.I)),
    (4, re.compile(r"\[LEVELS\]", re.I)),
    (5, re.compile(r"\bOpened\b", re.I)),
    (6, re.compile(r"\bClosed\b.*PnL=", re.I)),
    (7, re.compile(r"Heartbeat OK", re.I)),
    (8, re.compile(r"\[SCAN\].*near-miss", re.I)),
]

_LOGGER_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*\|\s*\w+\s*\|\s*[\w.]+\s*\|\s*(.+)$"
)
_TIME_SUFFIX = re.compile(r"\|\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*$")


def trading_log_path(*, heartbeat_path: str | Path | None = None) -> Path:
    if heartbeat_path:
        root = Path(heartbeat_path).resolve().parent.parent
    else:
        root = project_root()
    return root / "logs" / "trading.log"


def tail_trading_log(
    *,
    heartbeat_path: str | Path | None = None,
    lines: int = 20,
) -> list[str]:
    log_file = trading_log_path(heartbeat_path=heartbeat_path)
    if not log_file.is_file():
        return []
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return [ln for ln in content[-max(1, lines) :] if ln.strip()]
    except OSError:
        return []


def _line_priority(line: str) -> int | None:
    for priority, pattern in _ACTIVITY_PATTERNS:
        if pattern.search(line):
            return priority
    return None


def _extract_time_hint(line: str) -> str:
    m = _LOGGER_LINE.match(line.strip())
    if m:
        return m.group(1).split()[1][:5] + " UTC"  # HH:MM UTC
    m = _TIME_SUFFIX.search(line)
    if m:
        return m.group(1).split()[1][:5] + " UTC"
    return ""


def format_log_line(raw: str) -> str:
    """Turn a raw log line into a short human-readable phrase."""
    line = raw.strip()
    if not line:
        return ""

    if "systemd[1]:" in line or "Stopping futures-trading-bot" in line:
        return ""

    # Logger format: timestamp | LEVEL | module | message
    m = _LOGGER_LINE.match(line)
    if m:
        msg = m.group(2).strip()
        time_hint = m.group(1).split()[1][:5]
        if "notifier.telegram" in line or "Telegram send failed" in msg:
            if "404" in msg or "Not Found" in msg:
                return f"Error Telegram: token invalid · {time_hint} UTC"
            return f"Error Telegram · {time_hint} UTC"
        if msg.startswith("Opened "):
            return f"{msg} · {time_hint} UTC"
        if "PnL=" in msg or msg.startswith("Closed "):
            return f"{msg} · {time_hint} UTC"
        if "Heartbeat OK" in msg:
            return f"Heartbeat aktif · {time_hint} UTC"
        if "Order failed" in msg or "Close order failed" in msg:
            return f"{msg[:80]} · {time_hint} UTC"
        return f"{msg[:100]} · {time_hint} UTC"

    # Console-style lines (stdout captured in log if present)
    time_hint = _extract_time_hint(line)
    suffix = f" · {time_hint}" if time_hint else ""

    if "[EXECUTION] OPEN" in line:
        body = line.split("[EXECUTION] OPEN", 1)[-1].strip().split("|")[0].strip()
        return f"OPEN {body}{suffix}"
    if "[EXECUTION] REJECTED" in line:
        body = line.split("[EXECUTION] REJECTED", 1)[-1].strip().split("|")[0].strip()
        return f"REJECTED {body}{suffix}"
    if "[PICK]" in line:
        body = line.split("[PICK]", 1)[-1].strip().split("|")[0].strip()
        return f"PICK {body}{suffix}"
    if "[LEVELS]" in line:
        body = line.split("[LEVELS]", 1)[-1].strip().split("|")[0].strip()
        return f"SL/TP {body}{suffix}"
    if "[SCAN]" in line and "near-miss" in line.lower():
        return f"Near-miss {line.split('[SCAN]', 1)[-1].strip()[:60]}{suffix}"

    return line[:120]


def summarize_last_activity(
    lines: list[str] | None = None,
    *,
    heartbeat_path: str | Path | None = None,
    tail_lines: int = 30,
) -> str | None:
    """Pick the single most relevant recent activity line."""
    if lines is None:
        lines = tail_trading_log(heartbeat_path=heartbeat_path, lines=tail_lines)
    if not lines:
        return None

    best: tuple[int, int, str] | None = None  # (priority, index, formatted)
    for idx, raw in enumerate(reversed(lines)):
        priority = _line_priority(raw)
        if priority is None:
            continue
        formatted = format_log_line(raw)
        if not formatted:
            continue
        candidate = (priority, idx, formatted)
        if best is None or candidate[0] < best[0] or (
            candidate[0] == best[0] and candidate[1] < best[1]
        ):
            best = candidate

    return best[2] if best else None

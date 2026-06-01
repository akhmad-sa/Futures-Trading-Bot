"""
Trading bot health — systemd unit state + optional heartbeat file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from notifier.heartbeat import heartbeat_age_seconds, read_heartbeat
from notifier.service_control import ServiceControl
from notifier.trade_status import resolve_data_path


def _tail_app_log(heartbeat_path: str, lines: int = 5) -> str:
    """Fallback when journalctl is not readable by the service user."""
    root = Path(heartbeat_path).resolve().parent.parent
    log_file = root / "logs" / "trading.log"
    if not log_file.is_file():
        return ""
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-max(1, lines) :]).strip()
    except OSError:
        return ""


@dataclass(frozen=True)
class TradingBotStatus:
    service_name: str
    active_state: str
    sub_state: str
    main_pid: str
    heartbeat: dict | None
    heartbeat_age_s: float | None
    recent_log: str

    def is_healthy(self, *, stale_after_s: float = 120.0) -> bool:
        if self.active_state != "active":
            return False
        if self.heartbeat_age_s is None:
            return True
        return self.heartbeat_age_s <= stale_after_s

    def format_message(self) -> str:
        hb = self.heartbeat or {}
        age = self.heartbeat_age_s
        age_txt = f"{age:.0f}s ago" if age is not None else "n/a"
        healthy = "✅" if self.is_healthy() else "⚠️"

        lines = [
            f"{healthy} Trading Bot Status",
            f"Service: {self.service_name}",
            f"State: {self.active_state} ({self.sub_state})",
            f"PID: {self.main_pid or '—'}",
            f"Heartbeat: {age_txt}",
        ]
        if hb:
            mode = hb.get("mode", "—")
            symbols = hb.get("symbols") or []
            open_pos = hb.get("open_positions", "—")
            lines.append(f"Mode: {mode}")
            if symbols:
                lines.append(f"Symbols: {', '.join(symbols)}")
            lines.append(f"Open positions: {open_pos}")
            for pos in hb.get("open_positions_detail") or []:
                if not isinstance(pos, dict):
                    continue
                sym = pos.get("symbol", "?")
                side = str(pos.get("side", "")).upper()
                entry = float(pos.get("entry_price") or 0.0)
                lines.append(f"  • {sym} {side} @ {entry:.4f}")
            if hb.get("last_error"):
                lines.append(f"Last error: {hb['last_error']}")
        if self.recent_log.strip():
            lines.append("")
            lines.append("Recent log:")
            lines.append(self.recent_log.strip())
        return "\n".join(lines)


def collect_trading_bot_status(
    service_name: str,
    *,
    heartbeat_path: str,
    log_lines: int = 5,
) -> TradingBotStatus:
    ctl = ServiceControl(service_name)
    props = ctl.show_properties()
    heartbeat = read_heartbeat(resolve_data_path(heartbeat_path))
    age = heartbeat_age_seconds(heartbeat)
    recent = ctl.recent_journal_lines(log_lines)
    if not recent:
        recent = _tail_app_log(heartbeat_path, log_lines)

    return TradingBotStatus(
        service_name=service_name,
        active_state=props.get("ActiveState", "unknown"),
        sub_state=props.get("SubState", "unknown"),
        main_pid=props.get("MainPID", ""),
        heartbeat=heartbeat,
        heartbeat_age_s=age,
        recent_log=recent,
    )

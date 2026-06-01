"""
Trading bot health — compact Telegram /status (systemd + heartbeat + app log).
"""

from __future__ import annotations

from dataclasses import dataclass

from notifier.heartbeat import heartbeat_age_seconds, read_heartbeat, resolve_data_path
from notifier.log_summary import summarize_last_activity
from notifier.service_control import ServiceControl


def _bot_label(service_name: str) -> str:
    if "live" in service_name:
        return "live"
    if "paper" in service_name:
        return "paper"
    return service_name.replace("futures-trading-bot-", "") or "bot"


def _state_label(active_state: str, sub_state: str) -> str:
    if active_state == "active" and sub_state == "running":
        return "running"
    if active_state == "active":
        return sub_state or active_state
    if active_state == "inactive":
        return "stopped"
    return active_state or "unknown"


@dataclass(frozen=True)
class TradingBotStatus:
    service_name: str
    active_state: str
    sub_state: str
    main_pid: str
    heartbeat: dict | None
    heartbeat_age_s: float | None
    heartbeat_path: str
    last_activity: str | None

    def is_healthy(self, *, stale_after_s: float = 120.0) -> bool:
        if self.active_state != "active":
            return False
        if self.heartbeat_age_s is None:
            return True
        return self.heartbeat_age_s <= stale_after_s

    def format_message(self) -> str:
        hb = self.heartbeat or {}
        healthy = self.is_healthy()
        icon = "✅" if healthy else "⚠️"
        mode = _bot_label(self.service_name)
        state = _state_label(self.active_state, self.sub_state)

        lines = [f"{icon} Bot {mode} — {state}"]

        symbols = hb.get("symbols") or []
        open_count = int(hb.get("open_positions") or 0)
        if symbols:
            sym_txt = " ".join(str(s) for s in symbols[:6])
            if len(symbols) > 6:
                sym_txt += " …"
            lines.append(f"Scan: {sym_txt} · posisi open: {open_count}")
        elif open_count:
            lines.append(f"Posisi open: {open_count}")

        for pos in hb.get("open_positions_detail") or []:
            if not isinstance(pos, dict):
                continue
            sym = pos.get("symbol", "?")
            side = str(pos.get("side", "")).upper()
            entry = float(pos.get("entry_price") or 0.0)
            lines.append(f"  {sym} {side} @ {entry:.4f}")

        age = self.heartbeat_age_s
        if age is not None:
            phase = hb.get("phase") or "running"
            lines.append(f"Sinyal: {age:.0f}s lalu · {phase}")
            if hb.get("last_error"):
                lines.append(f"Error: {str(hb['last_error'])[:80]}")
        else:
            lines.append("Sinyal: belum terdeteksi (restart paper setelah update)")

        if self.last_activity:
            lines.append(f"Terakhir: {self.last_activity}")

        return "\n".join(lines)


def collect_trading_bot_status(
    service_name: str,
    *,
    heartbeat_path: str,
    log_lines: int = 30,
) -> TradingBotStatus:
    ctl = ServiceControl(service_name)
    props = ctl.show_properties()
    resolved_hb = resolve_data_path(heartbeat_path)
    heartbeat = read_heartbeat(resolved_hb)
    age = heartbeat_age_seconds(heartbeat)
    activity = summarize_last_activity(heartbeat_path=heartbeat_path, tail_lines=log_lines)

    return TradingBotStatus(
        service_name=service_name,
        active_state=props.get("ActiveState", "unknown"),
        sub_state=props.get("SubState", "unknown"),
        main_pid=props.get("MainPID", ""),
        heartbeat=heartbeat,
        heartbeat_age_s=age,
        heartbeat_path=heartbeat_path,
        last_activity=activity,
    )

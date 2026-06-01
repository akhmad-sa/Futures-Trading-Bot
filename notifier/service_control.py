"""
systemd service control for the trading bot daemon.
Uses sudo when the process lacks direct systemctl privileges.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ALLOWED_ACTIONS = frozenset({"start", "stop", "restart", "reload", "status"})

_JOURNAL_HINTS = (
    "Hint: You are currently not seeing",
    "Users in groups",
    "Pass -q to turn off",
    "No journal files were opened",
    "insufficient permissions",
)


def _strip_journal_noise(text: str) -> str:
    if not text:
        return ""
    kept = [
        line
        for line in text.splitlines()
        if line.strip() and not any(h in line for h in _JOURNAL_HINTS)
    ]
    return "\n".join(kept).strip()


@dataclass(frozen=True)
class ServiceActionResult:
    action: str
    service_name: str
    ok: bool
    output: str

    def format_message(self) -> str:
        icon = "✅" if self.ok else "❌"
        return f"{icon} systemctl {self.action} {self.service_name}\n{self.output.strip() or '(no output)'}"


class ServiceControl:
    """Run limited systemctl commands against one unit."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

    def run(self, action: str) -> ServiceActionResult:
        action = action.lower().strip()
        if action not in _ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action: {action}")

        if action == "reload":
            daemon = self._exec(["daemon-reload"])
            restart = self._exec(["try-restart", self.service_name])
            ok = daemon.ok and restart.ok
            output = f"{daemon.output}\n{restart.output}".strip()
            return ServiceActionResult(action, self.service_name, ok, output)

        result = self._exec([action, self.service_name])
        return ServiceActionResult(action, self.service_name, result.ok, result.output)

    def show_properties(self) -> dict[str, str]:
        result = self._exec(
            [
                "show",
                self.service_name,
                "--property=ActiveState,SubState,MainPID,Result,ExecMainStatus",
                "--no-page",
            ],
            check=False,
        )
        props: dict[str, str] = {}
        for line in result.output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                props[key.strip()] = value.strip()
        return props

    def recent_journal_lines(self, lines: int = 5) -> str:
        cmd = [
            "journalctl",
            "-q",
            "-u",
            self.service_name,
            "-n",
            str(max(1, lines)),
            "--no-pager",
            "--output=short-iso",
        ]
        for prefix in ([], ["sudo", "-n"]):
            try:
                proc = subprocess.run(
                    [*prefix, *cmd],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                if prefix:
                    logger.debug("journalctl failed: %s", exc)
                    break
                continue

            combined = _strip_journal_noise(
                (proc.stdout or proc.stderr or "").strip()
            )
            if proc.returncode == 0 and combined:
                return combined
            if prefix and combined and "insufficient permissions" not in combined.lower():
                return combined

        return ""

    @dataclass(frozen=True)
    class _ExecResult:
        ok: bool
        output: str

    def _exec(self, args: list[str], *, check: bool = True) -> _ExecResult:
        base = ["systemctl", *args]
        for prefix in ([], ["sudo", "-n"]):
            cmd = [*prefix, *base]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                if prefix:
                    return self._ExecResult(False, str(exc))
                continue

            output = (proc.stdout or proc.stderr or "").strip()
            ok = proc.returncode == 0
            if ok or prefix:
                return self._ExecResult(ok, output)

        return self._ExecResult(False, "systemctl failed (try sudoers for fbot)")

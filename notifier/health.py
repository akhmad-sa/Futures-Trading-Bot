"""
VPS system health metrics (no extra dependencies — reads /proc and shutil).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VpsHealth:
    hostname: str
    uptime_seconds: float
    load_1: float
    load_5: float
    load_15: float
    cpu_count: int
    mem_total_mb: float
    mem_available_mb: float
    mem_used_pct: float
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_used_pct: float

    def format_message(self) -> str:
        uptime_h = self.uptime_seconds / 3600
        return (
            "🖥 VPS Health\n"
            f"Host: {self.hostname}\n"
            f"Uptime: {uptime_h:.1f}h\n"
            f"Load: {self.load_1:.2f} / {self.load_5:.2f} / {self.load_15:.2f} "
            f"({self.cpu_count} CPU)\n"
            f"Memory: {self.mem_used_pct:.1f}% used "
            f"({self.mem_available_mb:.0f} MB free / {self.mem_total_mb:.0f} MB)\n"
            f"Disk: {self.disk_used_pct:.1f}% used "
            f"({self.disk_free_gb:.1f} GB free / {self.disk_total_gb:.1f} GB)"
        )


def _read_meminfo() -> tuple[float, float]:
    total_kb = avail_kb = 0.0
    path = Path("/proc/meminfo")
    if not path.is_file():
        return 0.0, 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            total_kb = float(line.split()[1])
        elif line.startswith("MemAvailable:"):
            avail_kb = float(line.split()[1])
    return total_kb / 1024, avail_kb / 1024


def _read_loadavg() -> tuple[float, float, float]:
    try:
        parts = Path("/proc/loadavg").read_text(encoding="utf-8").split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except (OSError, IndexError, ValueError):
        return 0.0, 0.0, 0.0


def _read_uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, IndexError, ValueError):
        return 0.0


def collect_vps_health(*, root_path: str | Path = "/") -> VpsHealth:
    """Collect host metrics for monitoring dashboards / Telegram alerts."""
    root = Path(root_path)
    usage = shutil.disk_usage(root)
    total_mb, avail_mb = _read_meminfo()
    used_pct = 0.0
    if total_mb > 0:
        used_pct = max(0.0, min(100.0, (1.0 - avail_mb / total_mb) * 100.0))

    disk_total_gb = usage.total / (1024**3)
    disk_free_gb = usage.free / (1024**3)
    disk_used_gb = usage.used / (1024**3)
    disk_used_pct = (usage.used / usage.total * 100.0) if usage.total else 0.0

    load_1, load_5, load_15 = _read_loadavg()
    cpu_count = os.cpu_count() or 1

    return VpsHealth(
        hostname=os.uname().nodename,
        uptime_seconds=_read_uptime(),
        load_1=load_1,
        load_5=load_5,
        load_15=load_15,
        cpu_count=cpu_count,
        mem_total_mb=total_mb,
        mem_available_mb=avail_mb,
        mem_used_pct=used_pct,
        disk_total_gb=disk_total_gb,
        disk_used_gb=disk_used_gb,
        disk_free_gb=disk_free_gb,
        disk_used_pct=disk_used_pct,
    )

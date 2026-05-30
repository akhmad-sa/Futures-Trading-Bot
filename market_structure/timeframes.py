"""
Shared timeframe constants and helpers for multi-timeframe market structure.
"""

from __future__ import annotations

from typing import Dict

_TIMEFRAME_MS: Dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}

# Recommended pairings: strategy TF → structure TF
DEFAULT_STRUCTURE_FOR_STRATEGY: Dict[str, str] = {
    "1m": "15m",
    "3m": "15m",
    "5m": "1h",
    "15m": "1h",
    "30m": "4h",
    "1h": "4h",
    "4h": "1d",
}


def get_interval_ms(timeframe: str) -> int:
    """Return candle interval in milliseconds for a supported timeframe string."""
    interval = _TIMEFRAME_MS.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return interval


def validate_timeframe(timeframe: str) -> str:
    """Validate and return the timeframe string."""
    get_interval_ms(timeframe)
    return timeframe


def is_higher_timeframe(structure_tf: str, strategy_tf: str) -> bool:
    """True when *structure_tf* has a longer bar interval than *strategy_tf*."""
    return get_interval_ms(structure_tf) > get_interval_ms(strategy_tf)


def suggest_structure_timeframe(strategy_tf: str) -> str:
    """Return a sensible default structure TF for a given strategy TF."""
    return DEFAULT_STRUCTURE_FOR_STRATEGY.get(strategy_tf, "1h")

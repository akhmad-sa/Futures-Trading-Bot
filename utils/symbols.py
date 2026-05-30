"""CLI symbol parsing helpers."""

from __future__ import annotations

from typing import List


def canonical_symbol(raw: str) -> str:
    """
    Normalize user input to canonical form (e.g. ``BTCUSDT``).

    Accepts ``btcusdt``, ``BTC/USDT``, ``BTC/USDT:USDT``, etc.
    """
    s = raw.strip().upper()
    if not s:
        return ""
    if "/" in s:
        base, _, rest = s.partition("/")
        quote = rest.split(":")[0]
        return f"{base}{quote}"
    # Already canonical or compact form
    if ":" in s:
        return s.split(":")[0]
    return s


def parse_symbols(*values: str) -> List[str]:
    """
    Parse CLI symbol arguments into a deduplicated canonical list.

    Supports comma-separated tokens::
        parse_symbols("btcusdt,ethusdt") -> ["BTCUSDT", "ETHUSDT"]
        parse_symbols("BTCUSDT", "ETHUSDT") -> ["BTCUSDT", "ETHUSDT"]
    """
    seen: set[str] = set()
    result: List[str] = []
    for raw in values:
        for part in raw.split(","):
            sym = canonical_symbol(part)
            if sym and sym not in seen:
                seen.add(sym)
                result.append(sym)
    return result

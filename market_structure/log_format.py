"""Human-readable structure state lines for console / debug logs."""

from __future__ import annotations

from typing import Optional

from market_structure.bos_choch import StructureState


def format_structure_state(state: Optional[StructureState]) -> str:
    if state is None:
        return "trend=n/a bias=n/a effective=n/a last=n/a"

    parts = [
        f"trend={state.trend.value}",
        f"bias={state.bias.value}",
        f"effective={state.effective_trend.value}",
    ]
    if state.last_break is not None:
        parts.append(f"last={state.last_break.kind.value}")
    else:
        parts.append("last=none")

    flags = []
    if state.blocks_long_entry():
        flags.append("block_long")
    if state.blocks_short_entry():
        flags.append("block_short")
    if flags:
        parts.append("flags=" + ",".join(flags))
    return " ".join(parts)

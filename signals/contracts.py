from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────
# CORE EVENTS (FROZEN SCHEMA)
# ─────────────────────────────

@dataclass(frozen=True)
class BreakoutEvent:
    direction: str              # "above" | "below"
    candle_index: int
    line_price: float
    close_price: float
    timestamp_ms: int

    # optional metadata (NO ENGINE DEPENDENCY LOGIC)
    trendline_id: Optional[str] = None
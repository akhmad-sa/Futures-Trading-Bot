"""Scored entry candidate for portfolio symbol selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from risk.exit_levels import EntryRiskHints


@dataclass
class ProspectiveSignal:
    symbol: str
    side: str  # long | short
    score: float
    hints: EntryRiskHints
    reasons: Dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.symbol} {self.side.upper()} score={self.score:.0f}"

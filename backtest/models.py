"""
Data models for backtest trades and results.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TradeRecord:
    """Represents a single completed trade during a backtest."""

    symbol: str
    side: str  # "long" or "short"
    entry_time: float  # milliseconds
    exit_time: float   # milliseconds
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float                # realised PnL after fees & funding
    commission: float         # total commission (maker + taker)
    leverage: float = 1.0     # leverage used
    funding_paid: float = 0.0 # net funding paid (positive = paid, negative = received)
    close_reason: str = "signal"  # reason for closing: "signal", "stop_loss", "take_profit",
                                  # "max_drawdown", "end_of_backtest"

    @property
    def duration_ms(self) -> float:
        """Trade duration in milliseconds."""
        return self.exit_time - self.entry_time

    @property
    def duration_hours(self) -> float:
        """Trade duration in hours."""
        return self.duration_ms / 3_600_000.0

    def __str__(self) -> str:
        """Readable one‑line trade summary."""
        return (
            f"{self.side.upper():6s} | {self.symbol:10s} | "
            f"entry={self.entry_price:.2f} | exit={self.exit_price:.2f} | "
            f"size={self.quantity:.4f} | leverage={self.leverage} | "
            f"PnL={self.pnl:+.2f} | comm={self.commission:.2f} | "
            f"funding={self.funding_paid:+.2f} | "
            f"duration={self.duration_hours:.2f}h | "
            f"reason={self.close_reason}"
        )

"""
Risk management: position sizing, daily loss limits, cooldowns.
"""

from typing import Any
from decimal import Decimal


class RiskManager:
    """Central risk manager enforcing trading rules."""

    def __init__(self, config) -> None:
        self.config = config
        self.daily_loss = 0.0
        self.daily_trades = 0

    def can_open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        current_positions_count: int = 0,
    ) -> bool:
        """Check whether a new position can be opened."""
        if self.daily_loss >= self.config.max_daily_loss:
            return False
        if current_positions_count >= self.config.max_concurrent_trades:
            return False
        # Add cooldown / symbol cooldown checks here
        return True

    def calculate_position_size(
        self,
        capital: float,
        price: float,
        stop_loss: float | None = None,
    ) -> float:
        """
        Compute quantity based on fixed risk percentage.

        If stop_loss is provided, size = risk_amount / |price - stop_loss|.
        Otherwise size = risk_amount / price.
        """
        risk_amount = capital * self.config.risk_per_trade
        if stop_loss and price:
            risk_per_unit = abs(price - stop_loss)
            if risk_per_unit > 0:
                return risk_amount / risk_per_unit
        return risk_amount / price

    def update_daily_loss(self, loss: float) -> None:
        """Accumulate daily realised loss (negative number)."""
        self.daily_loss += loss

    def reset_daily(self) -> None:
        """Call this at the start of each trading day."""
        self.daily_loss = 0.0
        self.daily_trades = 0

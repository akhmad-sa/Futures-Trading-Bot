"""
Funding model based on a :class:`SimulationConfig`.

Simulates periodic funding payments for open positions.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from simulation.config import SimulationConfig
from simulation.types import FundingResult


class FundingModel:
    """Encapsulates funding logic for a backtest."""

    def __init__(self, config: SimulationConfig) -> None:
        self._funding_rate = config.funding_rate
        self._interval_hours = config.funding_interval_hours
        self._enabled = config.funding_enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def next_funding_time(self, entry_time_ms: int) -> datetime:
        """
        Return the first funding payment datetime after *entry_time_ms*.
        """
        entry_dt = datetime.fromtimestamp(
            entry_time_ms / 1000, tz=timezone.utc
        )
        hour_block = entry_dt.hour // self._interval_hours
        block_start_hour = hour_block * self._interval_hours
        return entry_dt.replace(
            hour=block_start_hour,
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(hours=self._interval_hours)

    def calculate_funding_fee(
        self, position_side: str, quantity: float, price: float
    ) -> FundingResult:
        """
        Compute the funding payment for a position at the given *price*.

        Returns a :class:`FundingResult`:
        - ``payment`` is negative if the long position pays (subtracted from balance).
          Short positions receive funding (positive payment).
        - ``fee`` is always the absolute value of the payment (for logging).
        """
        notional = quantity * price
        payment = notional * self._funding_rate
        if position_side == "short":
            payment = -payment  # short receives funding
        return FundingResult(payment=payment, fee=abs(payment))

    def apply_funding(
        self, position_side: str, quantity: float, price: float
    ) -> float:
        """
        Compute and return the funding payment amount (same as *payment* in
        :meth:`calculate_funding_fee`).

        This is a convenience alias for use inside the backtest engine.
        """
        return self.calculate_funding_fee(position_side, quantity, price).payment

    # ── Legacy alias for backward compatibility ──────────────────
    def payment(
        self, position_side: str, quantity: float, price: float
    ) -> float:
        return self.apply_funding(position_side, quantity, price)

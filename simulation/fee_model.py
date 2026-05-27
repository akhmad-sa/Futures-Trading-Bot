"""
Fee model based on a :class:`SimulationConfig`.

Provides utility methods to compute opening and closing commissions.
"""

from simulation.config import SimulationConfig
from simulation.types import FeeResult


class FeeModel:
    """Encapsulates maker/taker fee logic for a backtest."""

    def __init__(self, config: SimulationConfig) -> None:
        self._maker_fee = config.maker_fee
        self._taker_fee = config.taker_fee

    def calculate_entry_fee(self, quantity: float, price: float) -> float:
        """
        Fee paid when opening a position (maker fee assumed).
        """
        return quantity * price * self._maker_fee

    def calculate_exit_fee(self, quantity: float, price: float) -> float:
        """
        Fee paid when closing a position (taker fee assumed).
        """
        return quantity * price * self._taker_fee

    def calculate_total_fee(
        self, quantity: float, entry_price: float, exit_price: float
    ) -> FeeResult:
        """
        Compute both entry and exit fees and return them in a :class:`FeeResult`.
        """
        entry = self.calculate_entry_fee(quantity, entry_price)
        exit = self.calculate_exit_fee(quantity, exit_price)
        return FeeResult(entry_fee=entry, exit_fee=exit, total_fee=entry + exit)

    # ── Legacy aliases for backward compatibility ──────────────────
    def open_commission(self, quantity: float, price: float) -> float:
        return self.calculate_entry_fee(quantity, price)

    def close_commission(self, quantity: float, price: float) -> float:
        return self.calculate_exit_fee(quantity, price)

    def total_commission(
        self, quantity: float, entry_price: float, exit_price: float
    ) -> float:
        return self.calculate_total_fee(quantity, entry_price, exit_price).total_fee

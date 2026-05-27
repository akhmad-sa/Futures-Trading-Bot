"""
Fee model based on a :class:`SimulationConfig`.

Provides utility methods to compute opening and closing commissions.
"""

from simulation.config import SimulationConfig


class FeeModel:
    """Encapsulates maker/taker fee logic for a backtest."""

    def __init__(self, config: SimulationConfig) -> None:
        self._maker_fee = config.maker_fee
        self._taker_fee = config.taker_fee

    def open_commission(self, quantity: float, price: float) -> float:
        """
        Commission paid when opening a position (maker fee assumed).
        """
        return quantity * price * self._maker_fee

    def close_commission(self, quantity: float, price: float) -> float:
        """
        Commission paid when closing a position (taker fee assumed).
        """
        return quantity * price * self._taker_fee

    def total_commission(self, quantity: float, entry_price: float,
                         exit_price: float) -> float:
        """
        Sum of open and close commissions for a round‑trip trade.
        """
        return (self.open_commission(quantity, entry_price) +
                self.close_commission(quantity, exit_price))

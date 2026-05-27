"""
Slippage model based on a :class:`SimulationConfig`.

Applies a fractional slippage to entry and exit prices expressed in
basis points.
"""

from simulation.config import SimulationConfig
from simulation.utils import bps_to_fraction


class SlippageModel:
    """Encapsulates slippage logic for a backtest."""

    def __init__(self, config: SimulationConfig) -> None:
        self._slippage_frac = config.slippage  # already converted to fraction

    def apply_buy_slippage(self, price: float) -> float:
        """
        Return the executed buy price after slippage (buyers pay more).
        """
        return price * (1 + self._slippage_frac)

    def apply_sell_slippage(self, price: float) -> float:
        """
        Return the executed sell price after slippage (sellers receive less).
        """
        return price * (1 - self._slippage_frac)

    def apply_execution_slippage(self, side: str, price: float) -> float:
        """
        Apply slippage based on the side of the trade.

        Parameters
        ----------
        side : str
            ``'long'`` (buy) or ``'short'`` (sell).
        price : float
            Reference price.

        Returns
        -------
        float
            Price after slippage.
        """
        if side == "long":
            return self.apply_buy_slippage(price)
        else:
            return self.apply_sell_slippage(price)

    # ── Legacy aliases for backward compatibility ──────────────────
    def entry_price(self, side: str, price: float) -> float:
        return self.apply_execution_slippage(side, price)

    def exit_price(self, side: str, price: float) -> float:
        # When closing a long position we sell (sell slippage)
        # When closing a short position we buy back (buy slippage)
        if side == "long":
            return self.apply_sell_slippage(price)
        else:
            return self.apply_buy_slippage(price)

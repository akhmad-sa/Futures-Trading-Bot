"""
Centralised simulation configuration for the backtest engine.

All fee, slippage, funding, and latency parameters are defined here
to avoid constructor parameter explosion in :class:`BacktestEngine`.
"""

from dataclasses import dataclass, field
from simulation.utils import bps_to_fraction


@dataclass
class SimulationConfig:
    """
    All parameters that influence how trades are simulated during a backtest.

    Attributes
    ----------
    maker_fee : float
        Fee rate applied when a limit order adds liquidity (default 0.001 = 0.1%).
    taker_fee : float
        Fee rate applied when a market order removes liquidity (default 0.001 = 0.1%).
    slippage_bps : float
        Slippage expressed in basis points (default 10 bps = 0.1%).
    funding_rate : float
        Funding rate per interval (default 0.0).
    funding_enabled : bool
        Enable / disable funding payments (default True).
    funding_interval_hours : int
        Number of hours between funding payments (default 8).
    latency_ms : float
        Simulated network latency in milliseconds (default 0).
    partial_fill_enabled : bool
        Enable / disable partial order fills (default False).
    liquidation_enabled : bool
        Enable / disable simulated liquidations (default False).
    latency_hooks : dict
        Optional dictionary of callable hooks for network latency simulation.
        Currently unused but reserved for future extensions.
    """
    maker_fee: float = 0.001
    taker_fee: float = 0.001
    slippage_bps: float = 10.0
    funding_rate: float = 0.0
    funding_enabled: bool = True
    funding_interval_hours: int = 8
    latency_ms: float = 0.0
    partial_fill_enabled: bool = False
    liquidation_enabled: bool = False
    latency_hooks: dict = field(default_factory=dict)

    @property
    def slippage(self) -> float:
        """Return slippage as a fractional multiplier (e.g. 0.001 for 0.1%)."""
        return bps_to_fraction(self.slippage_bps)

    @classmethod
    def default(cls) -> "SimulationConfig":
        return cls()

    @classmethod
    def binance_spot(cls) -> "SimulationConfig":
        return cls(maker_fee=0.001, taker_fee=0.001)

    @classmethod
    def binance_futures(cls) -> "SimulationConfig":
        return cls(maker_fee=0.0002, taker_fee=0.0004)

    @classmethod
    def bybit_futures(cls) -> "SimulationConfig":
        return cls(maker_fee=0.0001, taker_fee=0.0006)

    @classmethod
    def mexc_futures(cls) -> "SimulationConfig":
        return cls(maker_fee=0.0002, taker_fee=0.0006)

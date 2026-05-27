"""
Centralised simulation configuration for the backtest engine.

All fee, slippage, funding, and latency parameters are defined here
to avoid constructor parameter explosion in :class:`BacktestEngine`.
"""

from dataclasses import dataclass, field


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
    slippage : float
        Fractional price slippage applied to every order (default 0.001 = 0.1%).
    funding_rate : float
        Funding rate per interval (default 0.0).
    funding_interval_hours : int
        Number of hours between funding payments (default 8).
    latency_hooks : dict
        Optional dictionary of callable hooks for network latency simulation.
        Currently unused but reserved for future extensions.
    """
    maker_fee: float = 0.001
    taker_fee: float = 0.001
    slippage: float = 0.001
    funding_rate: float = 0.0
    funding_interval_hours: int = 8
    latency_hooks: dict = field(default_factory=dict)

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

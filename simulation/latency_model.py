"""
Latency model – placeholder for future websocket / live simulation.

Currently provides no‑op hooks that can be overridden once a real
latency simulation is required.
"""

from simulation.config import SimulationConfig


class LatencyModel:
    """
    Simulates network latency when placing orders or receiving market data.

    .. note::
        This is a placeholder.  Actual latency simulation (e.g. asyncio sleep)
        is intentionally omitted to preserve replay determinism for now.
    """

    def __init__(self, config: SimulationConfig) -> None:
        self._latency_ms = config.latency_ms

    async def apply_order_latency(self) -> None:
        """
        Wait for the configured latency before an order reaches the exchange.

        Current implementation is a no‑op.
        """
        if self._latency_ms > 0:
            # Future: await asyncio.sleep(self._latency_ms / 1000.0)
            pass

    async def apply_market_data_latency(self) -> None:
        """
        Wait for the configured latency before market data arrives.

        Current implementation is a no‑op.
        """
        if self._latency_ms > 0:
            pass

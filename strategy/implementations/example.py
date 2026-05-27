"""
Example strategy – demonstrates the new strategy architecture.

Placeholder: simply returns ``'hold'`` for all signals.
"""

from strategy.base import BaseStrategy


class ExampleStrategy(BaseStrategy):
    name = "example_strategy"
    description = "Example strategy that always holds."

    async def get_signal(self, symbol: str, candles: list) -> str:
        return "hold"

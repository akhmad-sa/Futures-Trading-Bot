"""
Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.

    Subclasses **must** define:
    - :attr:`name` – a human-readable identifier  (e.g. ``"ema_crossover"``)
    - :attr:`description` *(optional)* – a short description
    - :meth:`get_signal` – the core signal-generation logic
    """

    # ── Metadata (override in subclasses) ──────────────────────────
    name: Optional[str] = None
    description: Optional[str] = None

    def __init__(
        self,
        config: Any = None,
        symbols: Optional[List[str]] = None,
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        self.config = config
        self.symbols = symbols or []
        self.enabled = enabled

    @abstractmethod
    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Return a trading signal for the given symbol and candle history.

        The returned value must be one of: ``'long'``, ``'short'``,
        ``'close'``, or ``'hold'``.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"

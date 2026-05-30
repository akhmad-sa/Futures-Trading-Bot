"""
Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from market_structure.swing_structure import TrendStructure
from market_structure.bos_choch import StructureState


def _config_flag(config: Any, key: str, default: bool) -> bool:
    if config is None:
        return default
    val = getattr(config, key, default)
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return bool(val)


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
    manages_own_exits: bool = False

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
        self._structure_trend_override: Optional[TrendStructure] = None
        self._structure_state: Optional[StructureState] = None

    def set_structure_trend(self, trend: Optional[TrendStructure]) -> None:
        """Inject HTF market structure bias (from StructureFeed / live MTF)."""
        self._structure_trend_override = trend

    def set_structure_state(self, state: Optional[StructureState]) -> None:
        """Inject full structure snapshot (HH/HL trend + BOS/CHoCH bias)."""
        self._structure_state = state
        if state is not None:
            self._structure_trend_override = state.effective_trend

    @property
    def structure_state(self) -> Optional[StructureState]:
        return self._structure_state

    def get_structure_trend(self, fallback: TrendStructure) -> TrendStructure:
        """Return HTF structure when set, otherwise same-TF fallback."""
        if self._structure_trend_override is not None:
            return self._structure_trend_override
        return fallback

    def block_entry_on_counter_choch(self) -> bool:
        """Global/per-strategy flag: reject entries against recent CHoCH."""
        return _config_flag(
            self.config, "structure_block_entry_on_counter_choch", True
        )

    def choch_exit_enabled(self) -> bool:
        """Global/per-strategy flag: close open positions on counter CHoCH."""
        return _config_flag(self.config, "structure_choch_exit_enabled", False)

    def entry_blocked_by_choch(
        self, side: str, state: Optional[StructureState]
    ) -> bool:
        if not self.block_entry_on_counter_choch() or state is None:
            return False
        if side == "long":
            return state.blocks_long_entry()
        if side == "short":
            return state.blocks_short_entry()
        return False

    def choch_requests_exit(
        self,
        side: str,
        state: Optional[StructureState],
        entry_timestamp_ms: int,
    ) -> bool:
        if not self.choch_exit_enabled() or state is None:
            return False
        if side == "long":
            return state.choch_exits_long(entry_timestamp_ms)
        if side == "short":
            return state.choch_exits_short(entry_timestamp_ms)
        return False

    @abstractmethod
    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Return a trading signal for the given symbol and candle history.

        The returned value must be one of: ``'long'``, ``'short'``,
        ``'close'``, or ``'hold'``.

        TP/SL are handled globally by RiskManager. Strategies may set
        ``last_entry_hints`` (swing anchor, ATR) before returning entry signals.
        Optional ``close`` signals are for strategy-specific exits (e.g. trend).
        """
        ...

    def on_position_opened(self, side: str, entry_price: float) -> None:
        """Called by the engine after a fill opens a position."""

    def on_position_closed(self, reason: str, **kwargs: Any) -> None:
        """Called by the engine after any position close (TP/SL/trend/signal)."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"

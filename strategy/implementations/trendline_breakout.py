"""
Lightweight trendline breakout strategy.

Consumes structural events from :class:`MarketStructureEngine` instead of
performing pivot detection, trendline building, or breakout calculations
itself.
"""

import logging
from typing import Any, List, Optional

from strategy.base import BaseStrategy
from signals.structural_events import BreakoutEvent
from market_structure.engine import MarketStructureEngine

logger = logging.getLogger(__name__)


class TrendlineBreakoutStrategy(BaseStrategy):
    name = "trendline_breakout"
    description = (
        "Event‑driven trendline breakout strategy. "
        "Consumes structural events from MarketStructureEngine."
    )

    def __init__(
        self,
        config: Any = None,
        symbols: List[str] = None,
        enabled: bool = True,
        # Engine parameters (passed through)
        pivot_left: int = 2,
        pivot_right: int = 2,
        breakout_confirmation: int = 1,
        breakout_require_retest: bool = False,
        trendline_max_age: int = 100,
        min_breakout_bps: float = 0.0,
        volatility_filter_enabled: bool = False,
        min_atr_percent: float = 0.0,
        body_strength_filter_enabled: bool = False,
        min_body_ratio: float = 0.0,
        # Position management
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.04,
        max_holding_candles: int = 48,
        cooldown_after_loss_candles: int = 5,
        **kwargs,
    ):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)

        # Create the persistent engine
        self._engine = MarketStructureEngine(
            pivot_left=pivot_left,
            pivot_right=pivot_right,
            breakout_confirmation=breakout_confirmation,
            breakout_require_retest=breakout_require_retest,
            trendline_max_age=trendline_max_age,
            min_breakout_bps=min_breakout_bps,
            volatility_filter_enabled=volatility_filter_enabled,
            min_atr_percent=min_atr_percent,
            body_strength_filter_enabled=body_strength_filter_enabled,
            min_body_ratio=min_body_ratio,
        )

        # ── Position state ────────────────────────────────────────
        self._position: Optional[str] = None  # "long" or "short"
        self._entry_candle: int = -1
        self._entry_price: float = 0.0
        self._last_loss_candle: int = -cooldown_after_loss_candles - 1
        self._last_signal: str = "hold"
        self.cooldown_after_loss_candles = cooldown_after_loss_candles
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_holding_candles = max_holding_candles

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        """
        Generate a trading signal by consuming structural events.

        Returns ``'long'``, ``'short'``, ``'close'``, or ``'hold'``.
        """
        candle_index = len(candles) - 1
        current_candle = candles[-1]
        close = current_candle.close

        # ── 1. Feed candle to the engine ──────────────────────────
        events = self._engine.update(current_candle)

        # ── 2. Cooldown after loss ────────────────────────────────
        if candle_index - self._last_loss_candle < self.cooldown_after_loss_candles:
            return "hold"

        # ── 3. Process events ────────────────────────────────────
        signal = "hold"
        breakout_event: Optional[BreakoutEvent] = None

        for ev in events:
            # Capture the latest breakout
            if isinstance(ev, BreakoutEvent):
                breakout_event = ev

            # If a trendline we were trading on gets invalidated, close
            #if isinstance(ev, TrendlineInvalidatedEvent):
            #    if self._position is not None and not breakout_event:
            #        logger.info(
            #            "Trendline %s invalidated – closing position.",
            #            ev.trendline_id,
            #        )
            #        signal = "close"

        # ── 4. Position management ────────────────────────────────
        if self._position is None:
            if breakout_event is not None:
                if breakout_event.direction == "above":
                    signal = "long"
                    logger.info(
                        "Breakout ABOVE %s (close=%.2f) -> LONG",
                        breakout_event.trendline_id, breakout_event.close_price,
                    )
                elif breakout_event.direction == "below":
                    signal = "short"
                    logger.info(
                        "Breakout BELOW %s (close=%.2f) -> SHORT",
                        breakout_event.trendline_id, breakout_event.close_price,
                    )
        else:
            # Position open – check exit conditions
            exit_reason: Optional[str] = None

            # Opposite breakout
            if breakout_event is not None:
                if self._position == "long" and breakout_event.direction == "below":
                    exit_reason = "opposite_breakout"
                elif self._position == "short" and breakout_event.direction == "above":
                    exit_reason = "opposite_breakout"

            # Stop loss
            if exit_reason is None:
                if self._position == "long":
                    change = (close - self._entry_price) / self._entry_price
                    if change <= -self.stop_loss_pct:
                        exit_reason = "stop_loss"
                else:
                    change = (self._entry_price - close) / self._entry_price
                    if change <= -self.stop_loss_pct:
                        exit_reason = "stop_loss"

            # Take profit
            if exit_reason is None:
                if self._position == "long":
                    change = (close - self._entry_price) / self._entry_price
                    if change >= self.take_profit_pct:
                        exit_reason = "take_profit"
                else:
                    change = (self._entry_price - close) / self._entry_price
                    if change >= self.take_profit_pct:
                        exit_reason = "take_profit"

            # Max holding candles
            if exit_reason is None:
                if candle_index - self._entry_candle >= self.max_holding_candles:
                    exit_reason = "max_holding"

            if exit_reason is not None:
                signal = "close"
                logger.info(
                    "Closing %s (close=%.2f, reason=%s)",
                    self._position.upper(), close, exit_reason,
                )
                if exit_reason in ("stop_loss", "opposite_breakout"):
                    self._last_loss_candle = candle_index

        # ── 5. Update position state on entry ─────────────────────
        if signal in ("long", "short") and self._position is None:
            self._position = signal
            self._entry_candle = candle_index
            self._entry_price = close
        elif signal == "close":
            self._position = None
            self._entry_candle = -1

        self._last_signal = signal
        return signal

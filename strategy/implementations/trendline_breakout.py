"""
Pine Script-style trendline channel breakout strategy.

Entry logic only: volume-confirmed breakout → retest entry with HH/HL filter.
Supports scored ``evaluate_prospect`` for portfolio multi-symbol selection.
"""

import logging
from typing import Any, List, Optional

from strategy.base import BaseStrategy
from strategy.prospective_signal import ProspectiveSignal
from strategy.signal_quality import score_retest_entry
from market_structure.channel_engine import PineChannelEngine
from market_structure.mtf import MarketStructureContext
from market_structure.bos_choch import StructureState
from market_structure.swing_structure import TrendStructure
from indicators.atr import atr
from risk.exit_levels import EntryRiskHints

logger = logging.getLogger(__name__)


class TrendlineBreakoutStrategy(BaseStrategy):
    name = "trendline_breakout"
    manages_own_exits = False
    description = (
        "Pine-style channel breakout: retest entry with HH/HL filter. "
        "Scored entries for portfolio mode. Global TP/SL via RiskManager."
    )

    def __init__(
        self,
        config: Any = None,
        symbols: List[str] = None,
        enabled: bool = True,
        pivot_len: int = 5,
        line_extension_bars: int = 10,
        vol_sma_period: int = 20,
        vol_multiplier: float = 2.5,
        retest_max_bars: int = 24,
        retest_min_bars_after_breakout: int = 2,
        require_structure_filter: bool = True,
        structure_tolerance_bps: float = 0.0,
        structure_grace_bars: int = 6,
        atr_period: int = 14,
        min_hold_bars: int = 3,
        cooldown_after_trade_candles: int = 24,
        min_signal_score: float = 70.0,
        require_confirmed_structure: bool = True,
        allow_pending_structure: bool = False,
        block_entry_on_counter_choch: Optional[bool] = None,
        choch_exit_enabled: Optional[bool] = None,
        **kwargs,
    ):
        super().__init__(config=config, symbols=symbols, enabled=enabled, **kwargs)

        self._block_entry_on_counter_choch_override = block_entry_on_counter_choch
        self._choch_exit_enabled_override = choch_exit_enabled
        self._local_structure_ctx: Optional[MarketStructureContext] = None
        self._entry_timestamp_ms: int = 0
        self._last_seen_choch_ts: int = 0

        self._engine = PineChannelEngine(
            pivot_len=pivot_len,
            line_extension_bars=line_extension_bars,
            vol_sma_period=vol_sma_period,
            vol_multiplier=vol_multiplier,
            structure_tolerance_bps=structure_tolerance_bps,
            retest_max_bars=retest_max_bars,
            retest_min_bars_after_breakout=retest_min_bars_after_breakout,
        )

        self.require_structure_filter = require_structure_filter
        self.structure_tolerance_bps = structure_tolerance_bps
        self.structure_grace_bars = structure_grace_bars
        self.atr_period = atr_period
        self.min_hold_bars = min_hold_bars
        self.cooldown_after_trade_candles = cooldown_after_trade_candles
        self.min_signal_score = float(min_signal_score)
        self.require_confirmed_structure = require_confirmed_structure
        self.allow_pending_structure = allow_pending_structure
        self.vol_multiplier = vol_multiplier

        self._position: Optional[str] = None
        self._entry_candle: int = -1
        self._last_trade_candle: int = -cooldown_after_trade_candles - 1
        self._last_signal: str = "hold"
        self.last_hold_reason: str = "waiting"
        self.last_exit_reason: Optional[str] = None
        self.last_entry_hints: Optional[EntryRiskHints] = None
        self.last_scan_score: Optional[float] = None

        self._pending_side: Optional[str] = None
        self._pending_until: int = -1
        self._pending_hints: Optional[EntryRiskHints] = None

    def _use_trend_exit(self) -> bool:
        return bool(getattr(self.config, "use_trend_exit", False))

    def _use_bos_choch(self) -> bool:
        val = getattr(self.config, "structure_use_bos_choch", True)
        if isinstance(val, str):
            return val.lower() in ("1", "true", "yes", "on")
        return bool(val)

    def block_entry_on_counter_choch(self) -> bool:
        if self._block_entry_on_counter_choch_override is not None:
            return self._block_entry_on_counter_choch_override
        return super().block_entry_on_counter_choch()

    def choch_exit_enabled(self) -> bool:
        if self._choch_exit_enabled_override is not None:
            return self._choch_exit_enabled_override
        return super().choch_exit_enabled()

    def _local_structure_context(self) -> MarketStructureContext:
        if self._local_structure_ctx is None:
            pivot_len = int(getattr(self.config, "structure_pivot_len", 5))
            tol = self.structure_tolerance_bps
            confirm = bool(getattr(self.config, "structure_break_confirm_close", True))
            self._local_structure_ctx = MarketStructureContext(
                pivot_len=pivot_len,
                tolerance_bps=tol,
                use_bos_choch=True,
                break_confirm_close=confirm,
            )
        return self._local_structure_ctx

    def _resolve_structure_state(self, candles: List[Any]) -> Optional[StructureState]:
        """HTF injected state, or local BOS/CHoCH context on strategy candles."""
        if self.structure_state is not None:
            return self.structure_state
        if not self._use_bos_choch():
            return None
        if not candles:
            return None
        return self._local_structure_context().update(candles)

    def _structure_trend(self, state: Optional[StructureState] = None) -> TrendStructure:
        """HTF bias when MTF feed is active; else channel engine on strategy TF."""
        if state is not None:
            return state.effective_trend
        return self.get_structure_trend(self._engine.trend_structure)

    def _structure_allows(
        self, side: str, state: Optional[StructureState] = None
    ) -> bool:
        if not self.require_structure_filter:
            pass
        elif state is not None:
            if side == "long" and not state.allows_long():
                return False
            if side == "short" and not state.allows_short():
                return False
        else:
            trend = self._structure_trend()
            if side == "long" and trend != TrendStructure.UPTREND:
                return False
            if side == "short" and trend != TrendStructure.DOWNTREND:
                return False

        if state is None:
            state = self.structure_state
        if self.entry_blocked_by_choch(side, state):
            return False
        return True

    def _in_cooldown(self, candle_index: int) -> bool:
        return candle_index - self._last_trade_candle < self.cooldown_after_trade_candles

    def _current_atr(self, candles: List[Any]) -> Optional[float]:
        if len(candles) < self.atr_period + 2:
            return None
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        values = atr(highs, lows, closes, self.atr_period)
        return values[-1] if values else None

    def _entry_hints(self, side: str, candle: Any, candles: List[Any]) -> EntryRiskHints:
        anchor = candle.low if side == "long" else candle.high
        return EntryRiskHints(
            stop_anchor=anchor,
            atr_value=self._current_atr(candles),
        )

    def _arm_pending(
        self, side: str, candle_index: int, hints: EntryRiskHints
    ) -> None:
        if not self.allow_pending_structure:
            return
        self._pending_side = side
        self._pending_until = candle_index + self.structure_grace_bars
        self._pending_hints = hints

    def _clear_pending(self) -> None:
        self._pending_side = None
        self._pending_until = -1
        self._pending_hints = None

    def on_position_opened(self, side: str, entry_price: float, **kwargs: Any) -> None:
        self._position = side
        if "candle_index" in kwargs:
            self._entry_candle = int(kwargs["candle_index"])
        if "timestamp_ms" in kwargs:
            self._entry_timestamp_ms = int(kwargs["timestamp_ms"])

    def on_position_closed(self, reason: str, **kwargs: Any) -> None:
        candle_index = kwargs.get("candle_index")
        if candle_index is not None:
            self._last_trade_candle = candle_index
        self._position = None
        self._entry_candle = -1
        self._entry_timestamp_ms = 0
        self._last_seen_choch_ts = 0
        self._engine.clear_pending_entries()
        self._clear_pending()

    async def evaluate_prospect(
        self, symbol: str, candles: List[Any]
    ) -> Optional[ProspectiveSignal]:
        """Return scored entry candidate or None (portfolio scan)."""
        if len(candles) < 2 or self._position is not None:
            return None

        candle_index = len(candles) - 1
        if self._in_cooldown(candle_index):
            return None

        candle = candles[-1]
        ch = self._engine.update(candles)
        state = self._resolve_structure_state(candles)
        structure_trend = self._structure_trend(state)
        self.last_scan_score = None

        candidates: list[tuple[str, float, dict, EntryRiskHints]] = []

        if ch.bull_retest:
            score, breakdown = score_retest_entry(
                "long", ch, candle, candles,
                vol_multiplier=self.vol_multiplier,
                require_confirmed_structure=self.require_confirmed_structure,
                structure_trend=structure_trend,
            )
            if score > 0 and self._structure_allows("long", state):
                candidates.append(("long", score, breakdown, self._entry_hints("long", candle, candles)))
            elif score > 0:
                breakdown = {**breakdown, "reject": "counter_choch_or_structure"}

        if ch.bear_retest:
            score, breakdown = score_retest_entry(
                "short", ch, candle, candles,
                vol_multiplier=self.vol_multiplier,
                require_confirmed_structure=self.require_confirmed_structure,
                structure_trend=structure_trend,
            )
            if score > 0 and self._structure_allows("short", state):
                candidates.append(("short", score, breakdown, self._entry_hints("short", candle, candles)))
            elif score > 0:
                breakdown = {**breakdown, "reject": "counter_choch_or_structure"}

        if self.allow_pending_structure and self._pending_side:
            if candle_index > self._pending_until:
                self._clear_pending()
            elif self._structure_allows(self._pending_side, state) and self._pending_hints:
                side = self._pending_side
                score, breakdown = score_retest_entry(
                    side, ch, candle, candles,
                    vol_multiplier=self.vol_multiplier,
                    require_confirmed_structure=self.require_confirmed_structure,
                    structure_trend=structure_trend,
                )
                if score >= self.min_signal_score * 0.9:
                    candidates.append((side, score * 0.95, breakdown, self._pending_hints))

        if not candidates:
            return None

        side, score, breakdown, hints = max(candidates, key=lambda x: x[1])
        self.last_scan_score = score

        if score < self.min_signal_score:
            logger.debug(
                "%s %s score=%.0f below min=%.0f (%s)",
                symbol, side, score, self.min_signal_score, breakdown,
            )
            self._arm_pending(side, candle_index, hints)
            return None

        logger.info(
            "%s prospect %s score=%.0f breakdown=%s",
            symbol, side.upper(), score, breakdown,
        )
        return ProspectiveSignal(
            symbol=symbol,
            side=side,
            score=score,
            hints=hints,
            reasons=breakdown,
        )

    async def get_exit_signal(self, symbol: str, candles: List[Any]) -> str:
        """Exit-only signal when holding a position."""
        if self._position is None or len(candles) < 2:
            return "hold"

        candle_index = len(candles) - 1
        candle = candles[-1]
        close = candle.close
        self.last_exit_reason = None

        ch = self._engine.update(candles)
        state = self._resolve_structure_state(candles)
        signal = "hold"

        if self._position == "long" and self._use_trend_exit():
            bars_held = candle_index - self._entry_candle
            if (
                bars_held >= self.min_hold_bars
                and ch.lower_price is not None
                and close < ch.lower_price
            ):
                signal = "close"
                self.last_exit_reason = "trend_exit"
        elif self._position == "short" and self._use_trend_exit():
            bars_held = candle_index - self._entry_candle
            if (
                bars_held >= self.min_hold_bars
                and ch.upper_price is not None
                and close > ch.upper_price
            ):
                signal = "close"
                self.last_exit_reason = "trend_exit"

        if signal == "hold" and self._position is not None and self.choch_exit_enabled():
            bars_held = candle_index - self._entry_candle
            entry_ts = self._entry_timestamp_ms or candles[self._entry_candle].timestamp
            if bars_held >= self.min_hold_bars and self.choch_requests_exit(
                self._position, state, entry_ts
            ):
                brk = state.last_break if state else None
                if brk and brk.timestamp_ms > self._last_seen_choch_ts:
                    signal = "close"
                    self.last_exit_reason = "choch_exit"
                    self._last_seen_choch_ts = brk.timestamp_ms
                    logger.info(
                        "[CHOCH EXIT] Close %s position — %s @ %.2f",
                        self._position,
                        brk.kind.value if brk else "?",
                        brk.broken_level if brk else 0.0,
                    )

        if signal == "close":
            self._last_trade_candle = candle_index

        return signal

    async def get_signal(self, symbol: str, candles: List[Any]) -> str:
        if len(candles) < 2:
            self.last_hold_reason = "waiting"
            return "hold"

        if self._position is not None:
            self._engine.clear_pending_entries()
            self._clear_pending()
            exit_sig = await self.get_exit_signal(symbol, candles)
            self.last_hold_reason = "in_trade" if exit_sig == "hold" else "waiting"
            self._last_signal = exit_sig
            return exit_sig

        prospect = await self.evaluate_prospect(symbol, candles)
        if prospect:
            candle_index = len(candles) - 1
            candle = candles[-1]
            self.last_entry_hints = prospect.hints
            self._position = prospect.side
            self._entry_candle = candle_index
            self._entry_timestamp_ms = candle.timestamp
            self._last_trade_candle = candle_index
            self._clear_pending()
            self._engine.clear_pending_entries()
            self._last_signal = prospect.side
            self.last_hold_reason = "waiting"
            return prospect.side

        candle_index = len(candles) - 1
        if self._in_cooldown(candle_index):
            self.last_hold_reason = "cooldown"
        elif self._pending_side:
            self.last_hold_reason = "pending_structure"
        elif state := self._resolve_structure_state(candles):
            if (
                self.block_entry_on_counter_choch()
                and (
                    state.blocks_long_entry() or state.blocks_short_entry()
                )
            ):
                self.last_hold_reason = "counter_choch"
        else:
            self.last_hold_reason = "waiting"

        self._last_signal = "hold"
        return "hold"

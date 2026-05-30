"""
Multi-timeframe market structure: HTF bias filter for LTF entry strategies.

Strategy candles (LTF) drive entries; structure candles (HTF) determine
uptrend / downtrend / neutral bias via HH/HL swing classification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from market_data.models.candle import Candle
from market_data.services.market_data_service import MarketDataService
from market_structure.pivots import detect_swing_highs, detect_swing_lows
from market_structure.bos_choch import (
    StructureBreakTracker,
    StructureBreakEvent,
    StructureState,
)
from market_structure.swing_structure import SwingStructureTracker, TrendStructure
from market_structure.timeframes import is_higher_timeframe, validate_timeframe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MultiTimeframeConfig:
    """Global multi-timeframe settings (strategy TF vs structure TF)."""

    strategy_timeframe: str
    structure_timeframe: str
    enabled: bool = True

    @property
    def is_active(self) -> bool:
        """True when HTF structure filter is separate from strategy candles."""
        if not self.enabled:
            return False
        if self.strategy_timeframe == self.structure_timeframe:
            return False
        return is_higher_timeframe(self.structure_timeframe, self.strategy_timeframe)

    @classmethod
    def resolve(cls, config: Any, **overrides: Any) -> "MultiTimeframeConfig":
        """
        Build MTF config from AppConfig with optional per-strategy overrides.

        Override keys: ``timeframe``, ``structure_timeframe``, ``structure_mtf_enabled``.
        """
        strategy_tf = validate_timeframe(
            str(overrides.get("timeframe") or getattr(config, "timeframe", "1m"))
        )
        structure_tf = validate_timeframe(
            str(
                overrides.get("structure_timeframe")
                or getattr(config, "structure_timeframe", strategy_tf)
            )
        )
        enabled = overrides.get(
            "structure_mtf_enabled",
            getattr(config, "structure_mtf_enabled", True),
        )
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes", "on")
        return cls(
            strategy_timeframe=strategy_tf,
            structure_timeframe=structure_tf,
            enabled=bool(enabled),
        )


class MarketStructureContext:
    """
    Incremental HH/HL swing tracker + BOS/CHoCH on a single candle series (typically HTF).

    Used as the directional bias filter before LTF entry logic runs.
    """

    def __init__(
        self,
        pivot_len: int = 5,
        tolerance_bps: float = 0.0,
        *,
        use_bos_choch: bool = True,
        break_confirm_close: bool = True,
        break_tolerance_bps: float = 0.0,
    ) -> None:
        self.pivot_len = pivot_len
        self.use_bos_choch = use_bos_choch
        self._structure = SwingStructureTracker(tolerance_bps=tolerance_bps)
        self._break_tracker = StructureBreakTracker(
            confirm_with_close=break_confirm_close,
            break_tolerance_bps=break_tolerance_bps,
        )
        self._candle_count = 0
        self._last_events: List[StructureBreakEvent] = []

    @property
    def trend(self) -> TrendStructure:
        return self._structure.trend

    @property
    def bias(self) -> TrendStructure:
        return self._break_tracker.bias

    @property
    def effective_trend(self) -> TrendStructure:
        return self.state.effective_trend

    @property
    def state(self) -> StructureState:
        return StructureState(
            trend=self._structure.trend,
            bias=self._break_tracker.bias,
            last_break=self._break_tracker.last_break,
        )

    @property
    def tracker(self) -> SwingStructureTracker:
        return self._structure

    @property
    def break_tracker(self) -> StructureBreakTracker:
        return self._break_tracker

    @property
    def last_break_events(self) -> List[StructureBreakEvent]:
        return list(self._last_events)

    def allows_long(self) -> bool:
        return self.state.allows_long()

    def allows_short(self) -> bool:
        return self.state.allows_short()

    def update(self, candles: List[Candle]) -> StructureState:
        """Process candles up to and including the latest bar."""
        self._last_events = []
        if not candles:
            return self.state

        idx = len(candles) - 1
        if idx + 1 > self._candle_count:
            self._ingest_new_pivots(candles, idx)
            if self.use_bos_choch:
                candle = candles[idx]
                self._last_events = self._break_tracker.on_candle_close(
                    idx,
                    candle.close,
                    candle.high,
                    candle.low,
                    candle.timestamp,
                )
            self._candle_count = idx + 1
        return self.state

    def _ingest_new_pivots(self, candles: List[Candle], idx: int) -> None:
        pivot_len = self.pivot_len
        if idx < 2 * pivot_len:
            return

        start = idx - 2 * pivot_len
        window = candles[start : idx + 1]
        if len(window) < 2 * pivot_len + 1:
            return

        pivot_bar = idx - pivot_len
        local_pivot = pivot_len

        highs = detect_swing_highs(window, pivot_len, pivot_len)
        if local_pivot in highs:
            price = candles[pivot_bar].high
            ts = candles[pivot_bar].timestamp
            self._structure.on_swing_high(pivot_bar, price, ts)
            if self.use_bos_choch:
                self._break_tracker.on_swing_high(pivot_bar, price, ts)

        lows = detect_swing_lows(window, pivot_len, pivot_len)
        if local_pivot in lows:
            price = candles[pivot_bar].low
            ts = candles[pivot_bar].timestamp
            self._structure.on_swing_low(pivot_bar, price, ts)
            if self.use_bos_choch:
                self._break_tracker.on_swing_low(pivot_bar, price, ts)


class StructureFeed:
    """
    Aligns HTF structure to an LTF replay timeline (no look-ahead).

    Advances the HTF context only for closed HTF bars whose open time is
    less than or equal to the current LTF bar timestamp.
    """

    def __init__(
        self,
        mtf_config: MultiTimeframeConfig,
        *,
        pivot_len: int = 5,
        tolerance_bps: float = 0.0,
        use_bos_choch: bool = True,
        break_confirm_close: bool = True,
        break_tolerance_bps: float = 0.0,
    ) -> None:
        self.mtf_config = mtf_config
        self._context = MarketStructureContext(
            pivot_len=pivot_len,
            tolerance_bps=tolerance_bps,
            use_bos_choch=use_bos_choch,
            break_confirm_close=break_confirm_close,
            break_tolerance_bps=break_tolerance_bps,
        )
        self._htf_candles: List[Candle] = []
        self._htf_idx = 0
        self._use_bos_choch = use_bos_choch
        self._break_confirm_close = break_confirm_close
        self._break_tolerance_bps = break_tolerance_bps

    @property
    def context(self) -> MarketStructureContext:
        return self._context

    @property
    def trend(self) -> TrendStructure:
        return self._context.effective_trend

    @property
    def state(self) -> StructureState:
        return self._context.state

    async def load(
        self,
        service: MarketDataService,
        exchange: str,
        symbol: str,
        *,
        limit: int = 10_000,
        since: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> None:
        """Fetch HTF candles for structure analysis."""
        self._htf_candles = await service.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=self.mtf_config.structure_timeframe,
            limit=limit,
            since=since,
            start_time=start_time,
            end_time=end_time,
        )
        self._htf_idx = 0
        self._context = MarketStructureContext(
            pivot_len=self._context.pivot_len,
            tolerance_bps=self._context.tracker.tolerance_bps,
            use_bos_choch=self._use_bos_choch,
            break_confirm_close=self._break_confirm_close,
            break_tolerance_bps=self._break_tolerance_bps,
        )
        logger.info(
            "[MTF] Loaded %d %s structure candles for %s (strategy TF=%s)",
            len(self._htf_candles),
            self.mtf_config.structure_timeframe,
            symbol,
            self.mtf_config.strategy_timeframe,
        )

    def sync_to(self, ltf_timestamp_ms: int) -> StructureState:
        """Advance HTF structure to match the current LTF bar (closed bars only)."""
        while self._htf_idx < len(self._htf_candles):
            bar = self._htf_candles[self._htf_idx]
            if bar.timestamp > ltf_timestamp_ms:
                break
            self._context.update(self._htf_candles[: self._htf_idx + 1])
            self._htf_idx += 1
        return self._context.state


async def load_structure_feeds(
    service: MarketDataService,
    symbols: List[str],
    exchange: str,
    mtf_config: MultiTimeframeConfig,
    *,
    pivot_len: int = 5,
    tolerance_bps: float = 0.0,
    use_bos_choch: bool = True,
    break_confirm_close: bool = True,
    break_tolerance_bps: float = 0.0,
    limit: int = 10_000,
    since: Optional[int] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> Dict[str, StructureFeed]:
    """Load per-symbol HTF structure feeds when MTF is active."""
    if not mtf_config.is_active:
        return {}

    feeds: Dict[str, StructureFeed] = {}
    for symbol in symbols:
        feed = StructureFeed(
            mtf_config,
            pivot_len=pivot_len,
            tolerance_bps=tolerance_bps,
            use_bos_choch=use_bos_choch,
            break_confirm_close=break_confirm_close,
            break_tolerance_bps=break_tolerance_bps,
        )
        await feed.load(
            service,
            exchange,
            symbol,
            limit=limit,
            since=since,
            start_time=start_time,
            end_time=end_time,
        )
        feeds[symbol] = feed
    return feeds

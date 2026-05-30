"""
Structure diagnostics for the file log (``logs/trading.log``).

Terminal output stays in ``utils.console`` (trade events only).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

from market_structure.bos_choch import StructureState
from market_structure.log_format import format_structure_state

logger = logging.getLogger(__name__)

StructureLogMode = Literal["off", "events", "full"]

_INTERESTING_SKIP_REASONS = frozenset(
    {"counter_choch", "pending_structure", "cooldown", "no_setup"}
)


class StructureEventLogger:
    """
    Emit structure lines to the file logger.

    Modes:
      - ``off``: nothing
      - ``events``: state changes, meaningful skips, near-miss scores
      - ``full``: every scan (file only — never stdout)
    """

    def __init__(
        self,
        *,
        mode: StructureLogMode = "off",
        structure_timeframe: str = "1h",
        near_miss_min: float = 80.0,
    ) -> None:
        self.mode = mode
        self.structure_timeframe = structure_timeframe
        self.near_miss_min = near_miss_min
        self._last_state: dict[str, str] = {}
        self._last_skip: dict[str, str] = {}
        self._last_near_score: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    @classmethod
    def from_config(cls, config: object) -> StructureEventLogger:
        mode = getattr(config, "resolved_structure_log_mode", None)
        if callable(mode):
            resolved = mode()
        else:
            resolved = getattr(config, "structure_log_mode", "off")
            if bool(getattr(config, "structure_log_verbose", False)) and resolved == "off":
                resolved = "full"
        return cls(
            mode=resolved,
            structure_timeframe=str(getattr(config, "structure_timeframe", "1h")),
            near_miss_min=float(getattr(config, "structure_log_near_miss_min", 80.0)),
        )

    def _ts(self, candle_time: datetime) -> str:
        return candle_time.strftime("%Y-%m-%d %H:%M:%S")

    def record_scan(
        self,
        symbol: str,
        state: Optional[StructureState],
        candle_time: datetime,
        *,
        hold_reason: str = "waiting",
        scan_score: Optional[float] = None,
    ) -> None:
        if self.mode == "off":
            return

        state_text = format_structure_state(state)
        ts = self._ts(candle_time)

        if self.mode == "full":
            note = ""
            if hold_reason and hold_reason not in ("waiting", "in_trade"):
                note = f" skip={hold_reason}"
            elif scan_score is not None and scan_score > 0:
                note = f" near_score={scan_score:.0f}"
            logger.info(
                "[STRUCTURE] %s TF=%s %s%s | %s",
                symbol,
                self.structure_timeframe,
                state_text,
                note,
                ts,
            )
            return

        prev_state = self._last_state.get(symbol)
        if prev_state != state_text:
            tag = "INIT" if prev_state is None else "CHANGE"
            logger.info(
                "[STRUCTURE] %s %s TF=%s %s | %s",
                symbol,
                tag,
                self.structure_timeframe,
                state_text,
                ts,
            )
            self._last_state[symbol] = state_text

        if hold_reason in _INTERESTING_SKIP_REASONS:
            prev_skip = self._last_skip.get(symbol)
            if prev_skip != hold_reason:
                logger.info(
                    "[STRUCTURE] %s skip=%s TF=%s %s | %s",
                    symbol,
                    hold_reason,
                    self.structure_timeframe,
                    state_text,
                    ts,
                )
                self._last_skip[symbol] = hold_reason

        if scan_score is not None and scan_score >= self.near_miss_min:
            prev_near = self._last_near_score.get(symbol)
            if prev_near is None or abs(scan_score - prev_near) >= 1.0:
                logger.info(
                    "[STRUCTURE] %s near_miss score=%.0f (min=%.0f) TF=%s %s | %s",
                    symbol,
                    scan_score,
                    self.near_miss_min,
                    self.structure_timeframe,
                    state_text,
                    ts,
                )
                self._last_near_score[symbol] = scan_score

    def record_pick(
        self,
        symbol: str,
        side: str,
        score: float,
        state: Optional[StructureState],
        candle_time: datetime,
        *,
        breakdown: Optional[dict] = None,
    ) -> None:
        if self.mode == "off":
            return
        state_text = format_structure_state(state)
        ts = self._ts(candle_time)
        detail = ""
        if breakdown:
            from strategy.signal_quality import format_breakdown

            formatted = format_breakdown(breakdown)
            if formatted:
                detail = f" detail={formatted}"
        logger.info(
            "[STRUCTURE] %s PICK %s score=%.0f TF=%s %s%s | %s",
            symbol,
            side.upper(),
            score,
            self.structure_timeframe,
            state_text,
            detail,
            ts,
        )

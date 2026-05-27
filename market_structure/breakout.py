"""
Breakout detection using trendlines.

Determines whether the current candle has broken through a support or
resistance trendline.  Supports optional retest confirmation.
"""

import logging
from typing import Optional, Tuple

from market_data.models.candle import Candle
from market_structure.trendline import Trendline

logger = logging.getLogger(__name__)


class BreakoutDetector:
    """
    Detects breakouts of a given trendline.

    Parameters
    ----------
    confirmation_candles : int
        Number of consecutive closes beyond the trendline required for confirmation.
    require_retest : bool
        Whether to require a retest of the trendline after breakout.
    """

    def __init__(
        self,
        confirmation_candles: int = 1,
        require_retest: bool = False,
    ):
        self._confirmation = confirmation_candles
        self._require_retest = require_retest
        self._consecutive_break_count = 0
        self._retest_observed = False
        self._last_breakout_direction: Optional[str] = None  # "above" or "below"

    def check_breakout(
        self, candle: Candle, trendline: Trendline, candle_index: int
    ) -> Optional[str]:
        """
        Check if the current candle closes beyond *trendline*.

        Returns ``'above'`` if price closes above resistance,
        ``'below'`` if price closes below support, or ``None`` if no
        confirmed breakout.

        When *require_retest* is True, a breakout is only confirmed after
        a subsequent candle retests the trendline (closes back to the
        line within a small tolerance).
        """
        line_price = trendline.price_at(candle_index)
        close = candle.close

        # Determine direction of break relative to trendline type
        direction: Optional[str] = None
        if trendline.is_support:
            # Support line – a break occurs when price closes below it
            if close < line_price:
                direction = "below"
        else:
            # Resistance line – a break occurs when price closes above it
            if close > line_price:
                direction = "above"

        # Update consecutive counter
        if direction == self._last_breakout_direction:
            self._consecutive_break_count += 1
        else:
            self._consecutive_break_count = 1 if direction is not None else 0
            self._last_breakout_direction = direction

        # Check confirmation count
        if self._consecutive_break_count >= self._confirmation and direction is not None:
            if self._require_retest:
                # After initial break, wait for a candle that closes back
                # near the line (within 0.1% tolerance)
                if self._retest_observed:
                    self._retest_observed = False  # reset
                    return direction
                # Check if this candle itself is a retest
                tolerance = line_price * 0.001
                if abs(close - line_price) <= tolerance:
                    self._retest_observed = True
                return None
            else:
                return direction

        # Reset retest flag if direction changed
        if direction is None:
            self._retest_observed = False

        return None

    def reset(self) -> None:
        """Reset internal state (for new trendline or fresh start)."""
        self._consecutive_break_count = 0
        self._retest_observed = False
        self._last_breakout_direction = None

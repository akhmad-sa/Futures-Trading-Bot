"""
Tests for Pine-style channel engine.
"""

from market_data.models.candle import Candle
from market_structure.channel_engine import PineChannelEngine


def _c(
    i: int,
    close: float,
    *,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1000.0,
) -> Candle:
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close) + 1
    l = low if low is not None else min(o, close) - 1
    return Candle(
        timestamp=1_700_000_000_000 + i * 3_600_000,
        open=o,
        high=h,
        low=l,
        close=close,
        volume=volume,
    )


class TestPineChannelEngine:
    def test_bull_breakout_then_retest_entry(self):
        """Breakout arms retest; bullish retest candle triggers entry signal."""
        engine = PineChannelEngine(
            pivot_len=1,
            line_extension_bars=20,
            vol_sma_period=3,
            vol_multiplier=0.5,
        )

        # Descending highs to form upper channel, then breakout + retest
        series = [
            _c(0, 110, high=110, low=108),
            _c(1, 105, high=105, low=103),
            _c(2, 100, high=100, low=98),
            _c(3, 98, high=99, low=97),
            _c(4, 97, high=98, low=96),
            _c(5, 96, high=97, low=95),
            _c(6, 95, high=96, low=94),
            _c(7, 96, high=97, low=95),
            # breakout bar — close crosses above upper, high volume
            _c(8, 101, open_=100, high=102, low=99, volume=5000),
            # retest bar — wick to line, close above, bullish body
            _c(9, 102, open_=100, high=103, low=100, volume=1000),
        ]

        results = []
        for i in range(len(series)):
            results.append(engine.update(series[: i + 1]))

        assert any(r.bull_breakout for r in results)
        assert results[-1].bull_retest is True
        assert results[-1].breakout_volume_ratio > 1.0
        assert results[-1].volume_ratio >= results[-1].breakout_volume_ratio

    def test_bear_breakdown_then_retest_entry(self):
        engine = PineChannelEngine(
            pivot_len=1,
            line_extension_bars=20,
            vol_sma_period=3,
            vol_multiplier=0.5,
        )

        series = [
            _c(0, 90, high=92, low=90),
            _c(1, 95, high=97, low=95),
            _c(2, 100, high=102, low=100),
            _c(3, 102, high=103, low=101),
            _c(4, 103, high=104, low=102),
            _c(5, 104, high=105, low=103),
            _c(6, 105, high=106, low=104),
            _c(7, 104, high=105, low=103),
            _c(8, 99, open_=100, high=101, low=98, volume=5000),
            _c(9, 98, open_=100, high=100, low=97, volume=1000),
        ]

        results = []
        for i in range(len(series)):
            results.append(engine.update(series[: i + 1]))

        assert any(r.bear_breakdown for r in results)
        assert results[-1].bear_retest is True

    def test_no_entry_without_volume_breakout(self):
        engine = PineChannelEngine(pivot_len=1, vol_sma_period=3, vol_multiplier=5.0)
        series = [
            _c(0, 110, high=110, low=108),
            _c(1, 105, high=105, low=103),
            _c(2, 100, high=100, low=98),
            _c(3, 98, high=99, low=97),
            _c(4, 97, high=98, low=96),
            _c(5, 96, high=97, low=95),
            _c(6, 95, high=96, low=94),
            _c(7, 96, high=97, low=95),
            _c(8, 101, open_=100, high=102, low=99, volume=100),
            _c(9, 102, open_=100, high=103, low=100, volume=100),
        ]
        results = [engine.update(series[: i + 1]) for i in range(len(series))]
        assert not any(r.bull_breakout for r in results)
        assert not any(r.bull_retest for r in results)

    def test_retest_window_expires(self):
        engine = PineChannelEngine(
            pivot_len=1,
            line_extension_bars=50,
            vol_sma_period=3,
            vol_multiplier=0.5,
            retest_max_bars=3,
            retest_min_bars_after_breakout=1,
        )
        base = [
            _c(0, 110, high=110, low=108),
            _c(1, 105, high=105, low=103),
            _c(2, 100, high=100, low=98),
            _c(3, 98, high=99, low=97),
            _c(4, 97, high=98, low=96),
            _c(5, 96, high=97, low=95),
            _c(6, 95, high=96, low=94),
            _c(7, 96, high=97, low=95),
            _c(8, 101, open_=100, high=102, low=99, volume=5000),
        ]
        for i in range(len(base)):
            engine.update(base[: i + 1])
        assert engine.wait_bull_retest is True

        # Drift without retest past expiry window
        for j in range(4):
            c = _c(9 + j, 100 + j * 0.1, open_=100, high=101, low=99)
            engine.update(base + [c])
        assert engine.wait_bull_retest is False

"""
Signal quality scoring for high-probability entries.

Target: strict filter → fewer trades, higher win rate.
"""

from __future__ import annotations

from typing import Any, List, Optional

from market_structure.channel_engine import ChannelUpdateResult
from market_structure.swing_structure import TrendStructure


def score_retest_entry(
    side: str,
    ch: ChannelUpdateResult,
    candle: Any,
    candles: List[Any],
    *,
    vol_multiplier: float,
    require_confirmed_structure: bool,
    structure_trend: Optional[TrendStructure] = None,
) -> tuple[float, dict]:
    """
    Score 0–100. Returns (score, breakdown dict).
    Hard reject → score 0 when mandatory checks fail.
    """
    breakdown: dict = {}
    close = candle.close
    trend = structure_trend if structure_trend is not None else ch.trend_structure

    if side == "long":
        if require_confirmed_structure and trend != TrendStructure.UPTREND:
            breakdown["reject"] = "structure_not_uptrend"
            return 0.0, breakdown
        if not ch.bull_retest:
            breakdown["reject"] = "no_bull_retest"
            return 0.0, breakdown
        if candle.close <= candle.open:
            breakdown["reject"] = "not_bullish_candle"
            return 0.0, breakdown
    else:
        if require_confirmed_structure and trend != TrendStructure.DOWNTREND:
            breakdown["reject"] = "structure_not_downtrend"
            return 0.0, breakdown
        if not ch.bear_retest:
            breakdown["reject"] = "no_bear_retest"
            return 0.0, breakdown
        if candle.close >= candle.open:
            breakdown["reject"] = "not_bearish_candle"
            return 0.0, breakdown

    score = 0.0

    # ── Structure alignment (0–35) ────────────────────────────────
    if side == "long" and trend == TrendStructure.UPTREND:
        score += 35
        breakdown["structure"] = 35
    elif side == "short" and trend == TrendStructure.DOWNTREND:
        score += 35
        breakdown["structure"] = 35
    elif not require_confirmed_structure:
        score += 10
        breakdown["structure"] = 10
    else:
        breakdown["reject"] = "structure_mismatch"
        return 0.0, breakdown

    # ── Volume conviction (0–25) ──────────────────────────────────
    # Retest entries inherit breakout volume (retest bar volume is often low).
    effective_vol = max(
        ch.volume_ratio or 0.0,
        ch.breakout_volume_ratio or 0.0,
    )
    breakdown["volume_ratio"] = round(effective_vol, 2)
    if effective_vol >= vol_multiplier * 2.0:
        score += 25
        breakdown["volume"] = 25
    elif effective_vol >= vol_multiplier * 1.5:
        score += 20
        breakdown["volume"] = 20
    elif effective_vol >= vol_multiplier or ch.high_volume:
        score += 12
        breakdown["volume"] = 12
    elif ch.bull_retest or ch.bear_retest:
        # Retest only arms after volume-confirmed breakout in channel engine.
        score += 10
        breakdown["volume"] = 10
        breakdown["volume_source"] = "breakout_confirmed"
    else:
        breakdown["reject"] = "volume_too_weak"
        return 0.0, breakdown

    # ── Retest timing (0–15) ──────────────────────────────────────
    elapsed = ch.retest_bars_elapsed or 0
    breakdown["retest_bars"] = elapsed
    if elapsed > 12:
        breakdown["retest"] = 0
        breakdown["retest_stale"] = True
    elif elapsed > 8:
        score += 5
        breakdown["retest"] = 5
        breakdown["retest_stale"] = True
    elif elapsed >= 3:
        score += 15
        breakdown["retest"] = 15
    elif elapsed >= 2:
        score += 10
        breakdown["retest"] = 10
    elif elapsed >= 1:
        score += 5
        breakdown["retest"] = 5

    # ── Candle body strength (0–15) ───────────────────────────────
    body = abs(candle.close - candle.open) / close if close > 0 else 0
    breakdown["body_pct"] = round(body * 100, 3)
    if body >= 0.004:
        score += 15
        breakdown["body"] = 15
    elif body >= 0.002:
        score += 10
        breakdown["body"] = 10
    elif body >= 0.001:
        score += 5
        breakdown["body"] = 5

    # ── Breakout memory / channel context (0–10) ──────────────────
    if ch.high_volume:
        score += 10
        breakdown["breakout_vol"] = 10

    return min(score, 100.0), breakdown


def format_breakdown(breakdown: dict) -> str:
    """Compact one-line score breakdown for terminal / logs."""
    if not breakdown:
        return ""
    if "reject" in breakdown:
        return f"REJECT={breakdown['reject']}"

    parts: list[str] = []
    if "structure" in breakdown:
        parts.append(f"struct={breakdown['structure']}")
    if "volume" in breakdown:
        vr = breakdown.get("volume_ratio", "?")
        src = breakdown.get("volume_source", "")
        suffix = f"({vr}x)" if vr != "?" else ""
        if src:
            suffix = f"({vr}x,{src})"
        parts.append(f"vol={breakdown['volume']}{suffix}")
    if "retest" in breakdown:
        bars = breakdown.get("retest_bars", "?")
        stale = ",stale" if breakdown.get("retest_stale") else ""
        parts.append(f"retest={breakdown['retest']}({bars}bars{stale})")
    if "body" in breakdown:
        bp = breakdown.get("body_pct", "?")
        parts.append(f"body={breakdown['body']}({bp}%)")
    if "breakout_vol" in breakdown:
        parts.append(f"brk={breakdown['breakout_vol']}")
    return " ".join(parts)

"""
Per-symbol strategy parameter overrides.

BTC uses class defaults + strict scoring baseline.
Alts get tighter filters; portfolio mode picks highest score across symbols.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Strict high-win-rate defaults (merged for every symbol unless overridden)
_STRICT_BASE: Dict[str, Any] = {
    "require_confirmed_structure": True,
    "allow_pending_structure": False,
    "require_structure_filter": True,
    "retest_min_bars_after_breakout": 2,
}

BUILTIN_SYMBOL_OVERRIDES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "trendline_breakout": {
        "BTCUSDT": {
            **_STRICT_BASE,
            "min_signal_score": 70,
            "vol_multiplier": 2.5,
            "cooldown_after_trade_candles": 24,
        },
        "ETHUSDT": {
            **_STRICT_BASE,
            "min_signal_score": 75,
            "vol_multiplier": 3.5,
            "cooldown_after_trade_candles": 36,
            "structure_grace_bars": 8,
        },
        "XRPUSDT": {
            **_STRICT_BASE,
            "min_signal_score": 72,
            "vol_multiplier": 3.0,
            "cooldown_after_trade_candles": 36,
            "structure_grace_bars": 8,
        },
        "DOGEUSDT": {
            **_STRICT_BASE,
            "min_signal_score": 72,
            "vol_multiplier": 3.0,
            "cooldown_after_trade_candles": 36,
            "structure_grace_bars": 8,
        },
    },
}


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def parse_symbol_strategy_params(raw: Any) -> Dict[str, Dict[str, Any]]:
    """Parse SYMBOL_STRATEGY_PARAMS from JSON string or dict."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        return json.loads(raw)
    if isinstance(raw, dict):
        return {
            _normalize_symbol(k): v for k, v in raw.items() if isinstance(v, dict)
        }
    return {}


def resolve_strategy_params(
    strategy_name: str,
    symbol: str,
    *,
    global_params: Optional[Dict[str, Any]] = None,
    strategy_entry: Optional[Dict[str, Any]] = None,
    config: Any = None,
) -> Dict[str, Any]:
    """
    Merge strategy kwargs for *symbol* (later keys win).

    Order: global ``params`` → built-in symbol overrides →
    ``symbol_params`` in strategy entry → ``SYMBOL_STRATEGY_PARAMS`` env.
    """
    sym = _normalize_symbol(symbol)
    merged: Dict[str, Any] = dict(global_params or {})

    builtin = BUILTIN_SYMBOL_OVERRIDES.get(strategy_name, {}).get(sym, {})
    merged.update(builtin)

    if strategy_entry:
        entry_symbol_params = strategy_entry.get("symbol_params") or {}
        if sym in entry_symbol_params:
            merged.update(entry_symbol_params[sym])

    if config is not None:
        cfg_params = parse_symbol_strategy_params(
            getattr(config, "symbol_strategy_params", {})
        )
        if sym in cfg_params:
            merged.update(cfg_params[sym])
        # Global MIN_SIGNAL_SCORE from AppConfig (.env) overrides built-in per-symbol floor
        fields_set = getattr(config, "model_fields_set", set())
        if "min_signal_score" in fields_set:
            cfg_min = getattr(config, "min_signal_score", None)
            if cfg_min is not None:
                merged["min_signal_score"] = float(cfg_min)
                if float(cfg_min) < 70:
                    merged["require_confirmed_structure"] = False

    if merged:
        logger.info(
            "Strategy %s on %s params: %s",
            strategy_name,
            sym,
            merged,
        )
    else:
        logger.info(
            "Strategy %s on %s using class defaults",
            strategy_name,
            sym,
        )

    return merged


def list_symbols_for_strategy_entry(
    entry: Dict[str, Any],
    config: Any,
) -> list[str]:
    """Symbols targeted by a strategy config entry."""
    from utils.symbols import parse_symbols

    if entry.get("symbols"):
        return parse_symbols(*entry["symbols"])
    return parse_symbols(*getattr(config, "symbols", ["BTCUSDT"]))

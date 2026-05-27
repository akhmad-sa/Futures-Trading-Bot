"""
Discovery utilities for available strategies and exchanges.

Strategy discovery is delegated to :mod:`strategy.discovery`.
Exchange discovery remains here.
"""

import logging
from pathlib import Path
from typing import Dict, List, Type

from strategy.base import BaseStrategy
from strategy.discovery import (
    discover_and_register_strategies as _discover,
    get_available_strategy_names as _get_names,
)

logger = logging.getLogger(__name__)


# ── Strategy discovery (delegated) ────────────────────────────────

def list_strategies() -> List[str]:
    """Return a list of discovered strategy module names (stem names)."""
    return _get_names()


def discover_and_import_strategies() -> Dict[str, Type[BaseStrategy]]:
    """Discover and register all strategies, returning the registry."""
    return _discover()


def get_available_strategy_names() -> List[str]:
    """Return sorted strategy metadata names."""
    return _get_names()


# ── Exchange discovery (unchanged) ────────────────────────────────

def list_exchanges() -> List[str]:
    """Return a list of discovered exchange adapter names from exchange/adapters/."""
    adapters_dir = Path("exchange/adapters")
    if not adapters_dir.exists():
        logger.warning("Exchange adapters directory 'exchange/adapters/' does not exist.")
        return []
    names = [
        f.stem
        for f in adapters_dir.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    ]
    if names:
        logger.debug("Discovered exchange adapters: %s", names)
    else:
        logger.warning("No exchange adapter files found in exchange/adapters/")
    return names

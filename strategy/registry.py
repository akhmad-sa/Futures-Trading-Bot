"""
Global strategy registry.

Strategies are registered once during discovery and can be retrieved
by their :attr:`~strategy.base.BaseStrategy.name` from anywhere in
the application without re‑discovering.
"""

import logging
from typing import Dict, Type

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)

# ── Global registry ───────────────────────────────────────────────
STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def register_strategy(name: str, cls: Type[BaseStrategy]) -> None:
    """
    Register a strategy class under *name*.

    If the name is already registered the registration is **skipped**
    and a warning is logged (no exception raised).
    """
    if name in STRATEGY_REGISTRY:
        logger.warning(
            "Duplicate strategy name '%s' – already registered as %s; skipping.",
            name,
            STRATEGY_REGISTRY[name].__name__,
        )
        return
    STRATEGY_REGISTRY[name] = cls


def get_strategy(name: str) -> Type[BaseStrategy]:
    """
    Return the strategy class registered under *name*.

    Raises ``KeyError`` if no strategy with that name is registered.
    """
    if name not in STRATEGY_REGISTRY:
        raise KeyError(
            f"Strategy '{name}' is not registered. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}"
        )
    return STRATEGY_REGISTRY[name]


def list_registered_strategies() -> Dict[str, Type[BaseStrategy]]:
    """Return a copy of the current registry."""
    return dict(STRATEGY_REGISTRY)


def clear_registry() -> None:
    """Remove all registered strategies (useful for testing)."""
    STRATEGY_REGISTRY.clear()

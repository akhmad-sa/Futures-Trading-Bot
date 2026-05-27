"""
Global strategy registry.

Strategies are registered once during discovery and can be retrieved
by their :attr:`~strategy.base.BaseStrategy.name` from anywhere in
the application without re‑discovering.
"""

from typing import Dict, Type

from strategy.base import BaseStrategy

# ── Global registry ───────────────────────────────────────────────
STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def register_strategy(name: str, cls: Type[BaseStrategy]) -> None:
    """
    Register a strategy class under *name*.

    Raises ``ValueError`` if the name is already registered.
    """
    if name in STRATEGY_REGISTRY:
        raise ValueError(
            f"Duplicate strategy name '{name}' – already registered "
            f"as {STRATEGY_REGISTRY[name].__name__}. "
            "Each strategy must have a unique 'name' attribute."
        )
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

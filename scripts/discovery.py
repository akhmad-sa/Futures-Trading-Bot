"""
Discovery utilities for available strategies and exchanges.

Scans the appropriate directories for Python modules (excluding __init__.py)
and returns a list of their stem names.  Also provides functions to
dynamically import strategy modules, validate them, and return their
:class:`BaseStrategy` subclasses.
"""

import importlib
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


def list_strategies() -> List[str]:
    """Return a list of discovered strategy names from the strategy/ directory."""
    strategies_dir = Path("strategy")
    if not strategies_dir.exists():
        logger.warning("Strategy directory 'strategy/' does not exist.")
        return []
    names = [
        f.stem
        for f in strategies_dir.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    ]
    if names:
        logger.info("Discovered strategy files: %s", names)
    else:
        logger.warning("No strategy files found in strategy/")
    return names


def load_strategy_module(module_name: str) -> Optional[Type[BaseStrategy]]:
    """
    Import a strategy module and return the first :class:`BaseStrategy` subclass.

    If the module cannot be imported, or contains no valid subclass, ``None`` is
    returned and a warning is logged.
    """
    full_module = f"strategy.{module_name}"
    try:
        mod = importlib.import_module(full_module)
    except ImportError as e:
        logger.error("Failed to import strategy module '%s': %s", full_module, e)
        return None

    # Find subclasses of BaseStrategy in the module
    strategies = []
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and issubclass(attr, BaseStrategy) and attr is not BaseStrategy:
            strategies.append(attr)

    if not strategies:
        logger.warning("Module '%s' contains no BaseStrategy subclass", full_module)
        return None
    if len(strategies) > 1:
        logger.warning(
            "Module '%s' contains multiple strategies; using first: %s",
            full_module,
            strategies[0].__name__,
        )
    return strategies[0]


def discover_and_import_strategies() -> Dict[str, Type[BaseStrategy]]:
    """
    Discover all strategy modules, import them, validate against
    :class:`BaseStrategy`, and return a mapping of strategy name to class.
    """
    discovered: Dict[str, Type[BaseStrategy]] = {}
    for name in list_strategies():
        cls = load_strategy_module(name)
        if cls is not None:
            discovered[name] = cls
            logger.info("Registered strategy: %s -> %s", name, cls.__name__)
    return discovered


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
        logger.info("Discovered exchange adapters: %s", names)
    else:
        logger.warning("No exchange adapter files found in exchange/adapters/")
    return names

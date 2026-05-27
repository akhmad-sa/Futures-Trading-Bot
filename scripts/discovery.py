"""
Discovery utilities for available strategies and exchanges.

Scans the appropriate directories for Python modules (excluding __init__.py)
and returns a list of their stem names.  Also provides functions to
dynamically import strategy modules, validate them, and return their
:class:`BaseStrategy` subclasses along with their metadata name.
"""

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Type

from strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class StrategyInfo:
    """Holds the metadata name and class for a discovered strategy."""
    name: str
    cls: Type[BaseStrategy]


def list_strategies() -> List[str]:
    """Return a list of discovered strategy module names (stem names)."""
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
        logger.debug("Discovered strategy files: %s", names)
    else:
        logger.warning("No strategy files found in strategy/")
    return names


def load_strategy_module(module_name: str) -> Optional[StrategyInfo]:
    """
    Import a strategy module and return a :class:`StrategyInfo` with the
    strategy's metadata name and class.

    The metadata name is obtained from the class attribute ``name`` if present;
    otherwise the class name is used as a fallback and a warning is logged.

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
    cls = strategies[0]

    # Extract metadata name
    name = getattr(cls, "name", None)
    if not name or not isinstance(name, str) or not name.strip():
        # Fallback to class name
        name = cls.__name__
        logger.warning(
            "Strategy class %s in module '%s' has no valid 'name' attribute; "
            "falling back to class name '%s'",
            cls.__name__, full_module, name,
        )

    return StrategyInfo(name=name, cls=cls)


def discover_and_import_strategies() -> Dict[str, Type[BaseStrategy]]:
    """
    Discover all strategy modules, import them, validate against
    :class:`BaseStrategy`, and return a mapping of strategy metadata name
    to class.

    Duplicate names are detected; the last discovered class wins and a warning
    is logged.
    """
    discovered: Dict[str, Type[BaseStrategy]] = {}
    module_names = list_strategies()
    for mod_name in module_names:
        info = load_strategy_module(mod_name)
        if info is None:
            continue
        if info.name in discovered:
            logger.warning(
                "Duplicate strategy name '%s' from module '%s'; overwriting previous.",
                info.name, mod_name,
            )
        discovered[info.name] = info.cls
        logger.info("Registered strategy: %s -> %s", info.name, info.cls.__name__)
    return discovered


def get_available_strategy_names() -> List[str]:
    """
    Return a sorted list of strategy metadata names discovered from the
    ``strategy/`` directory.
    """
    mapping = discover_and_import_strategies()
    return sorted(mapping.keys())


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

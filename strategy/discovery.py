"""
Discovery and registration of strategy implementations.

Scans ``strategy/implementations/`` for Python modules (excluding
``__init__.py``), imports them, validates that they contain exactly one
:class:`BaseStrategy` subclass with a valid ``name`` attribute, and
registers them in :data:`strategy.registry.STRATEGY_REGISTRY`.

Discovery is **idempotent** – once the registry is populated subsequent
calls return immediately without re‑scanning the filesystem.
"""

import importlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from strategy.base import BaseStrategy
from strategy.registry import register_strategy, list_registered_strategies, clear_registry

logger = logging.getLogger(__name__)

# Directory that holds concrete strategy implementations
IMPLEMENTATIONS_DIR = Path("strategy") / "implementations"


def discover_and_register_strategies() -> Dict[str, Type[BaseStrategy]]:
    """
    Scan ``strategy/implementations/``, import each module, validate,
    and register every valid strategy.  Returns the updated registry.

    This function is **idempotent**.  If the registry already contains
    entries, it returns immediately without scanning again.
    """
    # ── Idempotency guard ─────────────────────────────────────────
    current = list_registered_strategies()
    if current:
        logger.debug("Strategy registry already populated (%d strategies); skipping re‑discovery.", len(current))
        return current

    if not IMPLEMENTATIONS_DIR.exists():
        logger.warning("Strategy implementations directory '%s/' does not exist.", IMPLEMENTATIONS_DIR)
        return {}

    module_names = [
        f.stem
        for f in IMPLEMENTATIONS_DIR.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    ]

    if not module_names:
        logger.info("No strategy implementation files found in '%s/'.", IMPLEMENTATIONS_DIR)
        return {}

    for mod_name in module_names:
        full_module = f"strategy.implementations.{mod_name}"
        try:
            mod = importlib.import_module(full_module)
        except ImportError as e:
            logger.error("Failed to import strategy module '%s': %s", full_module, e)
            continue

        # Find subclasses of BaseStrategy (excluding BaseStrategy itself)
        strategies = [
            attr
            for attr_name in dir(mod)
            if not attr_name.startswith("_")
            for attr in [getattr(mod, attr_name)]
            if isinstance(attr, type) and issubclass(attr, BaseStrategy) and attr is not BaseStrategy
        ]

        if not strategies:
            logger.warning("Module '%s' contains no BaseStrategy subclass; skipping.", full_module)
            continue

        if len(strategies) > 1:
            logger.warning(
                "Module '%s' contains multiple strategies; using first: %s",
                full_module,
                strategies[0].__name__,
            )

        cls = strategies[0]

        # Validate metadata
        name = getattr(cls, "name", None)
        if not name or not isinstance(name, str) or not name.strip():
            logger.warning(
                "Strategy class %s in module '%s' has no valid 'name' attribute; "
                "falling back to class name '%s'.",
                cls.__name__, full_module, cls.__name__,
            )
            name = cls.__name__

        try:
            register_strategy(name, cls)
            logger.info("Registered strategy: %s -> %s", name, cls.__name__)
        except ValueError as e:
            logger.error("Failed to register strategy '%s': %s", name, e)
            continue

    return list_registered_strategies()


def get_available_strategy_names() -> List[str]:
    """
    Return a sorted list of strategy names currently registered.

    This function triggers discovery **once** (idempotent).
    """
    registry = list_registered_strategies()
    if not registry:
        discover_and_register_strategies()
        registry = list_registered_strategies()
    return sorted(registry.keys())

"""
Dynamic strategy loading and registration.
"""

import logging
from typing import Any, Dict, List, Type, Optional

from strategy.base import BaseStrategy
from strategy.example import ExampleStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry of available strategy classes that can be dynamically loaded."""

    def __init__(self) -> None:
        self._strategies: Dict[str, Type[BaseStrategy]] = {}
        self._register_core()

    def _register_core(self) -> None:
        """Register built‑in strategy classes."""
        self.register("example_strategy", ExampleStrategy)
        # Add new strategies here as they are created

    def register(self, name: str, strategy_class: Type[BaseStrategy]) -> None:
        """Register a strategy class by name."""
        if not issubclass(strategy_class, BaseStrategy):
            raise ValueError(
                f"{strategy_class.__name__} is not a subclass of BaseStrategy"
            )
        self._strategies[name] = strategy_class
        logger.debug("Registered strategy '%s'", name)

    def get(self, name: str) -> Type[BaseStrategy]:
        """Get a strategy class by name."""
        cls = self._strategies.get(name)
        if cls is None:
            raise KeyError(f"Strategy '{name}' not registered")
        return cls

    def load_from_config(self, config) -> List[BaseStrategy]:
        """
        Instantiate strategies based on the config's 'strategies' list.

        Each item: dict with keys:
          - name: str (required)
          - enabled: bool (default True)
          - symbols: list[str] (optional; if not provided, use global symbols from config)
          - params: dict (optional, passed to strategy constructor)
        """
        strategies: List[BaseStrategy] = []
        global_symbols = getattr(config, "symbols", ["BTCUSDT"])
        strategy_configs = getattr(config, "strategies", [])

        for item in strategy_configs:
            name = item.get("name")
            if not name:
                logger.warning("Strategy config missing 'name', skipping")
                continue
            enabled = item.get("enabled", True)
            if not enabled:
                logger.info("Strategy '%s' disabled by config", name)
                continue
            symbols = item.get("symbols", global_symbols)
            params = item.get("params", {})

            try:
                strategy_class = self.get(name)
                # Merge global config with strategy‑specific parameters
                # Pass the whole config object, plus keyword arguments from params
                strategy = strategy_class(
                    config=config,
                    symbols=symbols,
                    enabled=enabled,
                    **params,
                )
                strategies.append(strategy)
                logger.info("Loaded strategy '%s' for symbols %s", name, symbols)
            except KeyError as exc:
                logger.error("Failed to load strategy '%s': %s", name, exc)

        return strategies

"""
Factory for creating perpetual-futures exchange adapters by name.

Registered venues: mexc, binance, bybit (see exchange/*.py).
"""

from typing import Dict, Type

from exchange.base import BaseExchange
from exchange.binance import BinanceExchange
from exchange.bybit import BybitExchange
from exchange.mexc import MEXCExchange
from exchange.paper_wrapper import PaperTradingExchange

_exchange_classes: Dict[str, Type[BaseExchange]] = {
    "binance": BinanceExchange,
    "bybit": BybitExchange,
    "mexc": MEXCExchange,
}


def register_exchange(name: str, cls: Type[BaseExchange]) -> None:
    """Register a custom exchange class."""
    _exchange_classes[name.lower()] = cls


def create_exchange(name: str, config: dict) -> BaseExchange:
    """
    Create an exchange instance by its name.

    The ``config`` dict should contain keys like 'api_key', 'api_secret',
    and any exchange‑specific options.
    """
    cls = _exchange_classes.get(name.lower())
    if cls is None:
        raise ValueError(
            f"Unknown exchange '{name}'. Available: {list(_exchange_classes.keys())}"
        )
    exchange = cls(config)
    if config.get("paper_simulate"):
        initial = float(config.get("paper_initial_balance", 10_000.0))
        return PaperTradingExchange(exchange, initial_balance=initial)
    return exchange

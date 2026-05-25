"""
Unified data models for orders, positions, and balances.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Order:
    """Unified order representation."""
    symbol: str
    order_id: str
    client_order_id: Optional[str]
    side: str                     # 'buy' / 'sell'
    type: str                     # 'market' / 'limit' / 'stop'
    status: str                   # 'open' / 'filled' / 'canceled' / 'partially_filled'
    price: float
    amount: float
    filled: float
    remaining: float
    cost: float
    timestamp: datetime
    exchange: str


@dataclass
class Position:
    """Unified position representation."""
    symbol: str
    side: str                     # 'long' / 'short' / 'neutral'
    size: float
    entry_price: float
    mark_price: float
    pnl: float
    leverage: int
    liquidation_price: float
    margin: float
    timestamp: datetime
    exchange: str


@dataclass
class Balance:
    """Unified balance representation."""
    total: float
    free: float
    used: float
    currency: str
    exchange: str

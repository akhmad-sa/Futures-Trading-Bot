"""
Event dataclasses used throughout the system.
"""

from dataclasses import dataclass


@dataclass
class OrderEvent:
    """Fired when an order status changes."""
    symbol: str
    order_id: str
    side: str          # buy / sell
    amount: float
    price: float
    status: str        # open / filled / cancelled


@dataclass
class FillEvent:
    """Emitted when an order is partially or fully filled."""
    symbol: str
    order_id: str
    side: str
    filled_amount: float
    fill_price: float
    commission: float


@dataclass
class PositionEvent:
    """Represents a change in an open position."""
    symbol: str
    size: float
    entry_price: float
    pnl: float

"""
Unified data models for orders, positions, and balances.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class Candle(BaseModel):
    """Unified candle representation."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class Order(BaseModel):
    """Unified order representation."""
    symbol: str
    id: str
    client_order_id: Optional[str] = None
    side: OrderSide
    type: OrderType
    status: OrderStatus
    price: Optional[float] = None
    amount: float
    filled: float
    remaining: float
    cost: float
    timestamp: datetime
    exchange: str
    info: Dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    """Unified position representation."""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    mark_price: float
    pnl: float
    leverage: int
    liquidation_price: Optional[float] = None
    margin: float
    timestamp: datetime
    exchange: str
    info: Dict[str, Any] = Field(default_factory=dict)


class Balance(BaseModel):
    """Unified balance representation."""
    total: float
    free: float
    used: float
    currency: str
    exchange: str

"""
Data models for backtesting.
"""

from dataclasses import dataclass


@dataclass
class TradeRecord:
    """Record of a single completed trade."""
    symbol: str
    side: str          # 'long' / 'short'
    entry_time: float
    exit_time: float
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    commission: float

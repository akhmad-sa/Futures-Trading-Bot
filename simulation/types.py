"""
Shared result types for the simulation subsystem.
"""

from dataclasses import dataclass


@dataclass
class FeeResult:
    """Result of a fee calculation."""
    entry_fee: float
    exit_fee: float
    total_fee: float


@dataclass
class SlippageResult:
    """Result of a slippage calculation."""
    buy_slippage: float
    sell_slippage: float


@dataclass
class FundingResult:
    """Result of a funding payment calculation."""
    payment: float
    fee: float

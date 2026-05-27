"""
Utility functions for the simulation subsystem.
"""


def bps_to_fraction(bps: float) -> float:
    """Convert basis points to a fractional multiplier (1 bps = 0.0001)."""
    return bps / 10_000.0


def fraction_to_bps(fraction: float) -> float:
    """Convert a fractional multiplier to basis points."""
    return fraction * 10_000.0

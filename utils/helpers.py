"""
Miscellaneous helper functions.
"""


def round_to_tick(price: float, tick_size: float) -> float:
    """Round a price to the nearest tick."""
    return round(price / tick_size) * tick_size


def format_float(value: float, decimals: int = 2) -> str:
    """Format a float to a fixed number of decimals."""
    return f"{value:.{decimals}f}"

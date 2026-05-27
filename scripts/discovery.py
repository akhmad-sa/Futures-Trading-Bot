"""
Discovery utilities for available strategies and exchanges.

Scans the appropriate directories for Python modules (excluding __init__.py)
and returns a list of their stem names.
"""

from pathlib import Path


def list_strategies() -> list:
    """Return a list of discovered strategy names from the strategies/ directory."""
    strategies_dir = Path("strategy")
    if not strategies_dir.exists():
        return []
    return [
        f.stem
        for f in strategies_dir.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    ]


def list_exchanges() -> list:
    """Return a list of discovered exchange adapter names from exchange/adapters/."""
    adapters_dir = Path("exchange/adapters")
    if not adapters_dir.exists():
        return []
    return [
        f.stem
        for f in adapters_dir.iterdir()
        if f.suffix == ".py" and f.stem != "__init__"
    ]

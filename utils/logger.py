"""
Logging configuration – verbose file log, quiet console.

All INFO/DEBUG diagnostics go to ``logs/trading.log`` only.
The terminal receives WARNING+ from the logging system; user-facing
trade flow uses ``utils.console`` instead.
"""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: str = "logs/trading.log") -> None:
    """Configure root logger: file=verbose, console=warnings only."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

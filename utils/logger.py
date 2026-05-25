"""
Logging configuration – console + file.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with stdout and rotating file handler."""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler("logs/trading.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

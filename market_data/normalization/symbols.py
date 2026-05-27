"""
Exchange‑aware symbol normalization.

Converts internal canonical symbols (e.g. ``BTCUSDT``, ``ETHUSDT``) into
the format expected by each exchange's REST API.

All input symbols are automatically uppercased before processing so that
lowercase input (e.g. ``solusdt``) works correctly.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Ordered list of known quote currencies – longer matches first.
_KNOWN_QUOTES = [
    "BUSD", "USDC", "USDT", "DAI", "TUSD", "USDP", "PAX",
    "USD", "EUR", "GBP", "JPY",
    "BTC", "ETH", "BNB", "SOL", "XRP",
]


def split_canonical(symbol: str) -> tuple[str, str]:
    """
    Split a canonical symbol (e.g. ``"BTCUSDT"``) into (base, quote).

    Heuristic: iterate over known quote currencies and return the first
    match that leaves at least one character for the base.  Falls back
    to trailing 4 characters (USDT assumption) if nothing matches.
    Input is uppercased automatically.
    """
    sym = symbol.upper()
    for quote in _KNOWN_QUOTES:
        if sym.endswith(quote) and len(sym) > len(quote):
            base = sym[: -len(quote)]
            return base, quote
    # Fallback – assume last 4 chars are the quote
    if len(sym) > 4:
        return sym[:-4], sym[-4:]
    # Last resort – treat last 3 as quote
    return sym[:-3], sym[-3:]


def normalize_symbol(exchange: str, symbol: str, *, market_type: str = "spot") -> str:
    """
    Convert the canonical *symbol* (no slashes) into the exchange‑native
    format expected by that exchange's API.

    The input symbol is automatically uppercased so that both
    ``"BTCUSDT"`` and ``"btcusdt"`` work.

    Parameters
    ----------
    exchange : str
        Lowercase exchange identifier (``"binance"``, ``"bybit"``, ``"mexc"``).
    symbol : str
        Canonical symbol, e.g. ``"BTCUSDT"`` or ``"solusdt"``.
    market_type : str
        ``"spot"`` or ``"future"`` (also "perp").  Relevant for Bybit/MEXC.

    Returns
    -------
    str
        Normalized symbol ready for the exchange API.

    Examples
    --------
    >>> normalize_symbol("binance", "BTCUSDT")
    'BTC/USDT'
    >>> normalize_symbol("bybit", "ETHUSDT", market_type="perp")
    'ETH/USDT:USDT'
    """
    base, quote = split_canonical(symbol)  # split_canonical already uppercases
    ex = exchange.lower()

    if ex == "binance":
        # Spot & USDⓈ‑M futures share the same format
        return f"{base}/{quote}"

    if ex in ("bybit", "mexc"):
        # For linear perpetual contracts the symbol includes the settlement
        # currency (equal to the quote for USDT pairs).
        if market_type in ("future", "perp", "linear"):
            return f"{base}/{quote}:{quote}"
        # Spot uses the same format as Binance
        return f"{base}/{quote}"

    # Default fallback
    logger.warning("Unknown exchange '%s' – falling back to base/quote format", exchange)
    return f"{base}/{quote}"

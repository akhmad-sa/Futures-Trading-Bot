"""
Exchange symbol normalization and validation.

Provides clean functions to convert canonical symbols (e.g. ``"SOLUSDT"``)
to exchange-native formats and vice versa.  All internal symbols are
stored in uppercase to avoid casing issues.
"""

from market_data.normalization.symbols import (
    normalize_symbol as _normalize_symbol,
    split_canonical as _split_canonical,
)


def normalize_symbol(symbol: str) -> str:
    """
    Normalize a user-supplied symbol to an uppercase canonical form.

    Example
    -------
    >>> normalize_symbol("solusdt")
    'SOLUSDT'
    >>> normalize_symbol("BTCUSDT")
    'BTCUSDT'
    """
    return symbol.upper()


def to_exchange_symbol(
    exchange: str, symbol: str, market_type: str = "perp"
) -> str:
    """
    Convert a canonical symbol (any case) to an exchange-native format.

    Parameters
    ----------
    exchange : str
        Lowercase exchange identifier (e.g. ``"binance"``, ``"bybit"``).
    symbol : str
        User-supplied symbol (e.g. ``"solusdt"``, ``"BTCUSDT"``).
    market_type : str
        ``"spot"``, ``"perp"``, or ``"future"``.

    Returns
    -------
    str
        Symbol ready to be passed to the exchange's API.

    Example
    -------
    >>> to_exchange_symbol("bybit", "solusdt", market_type="perp")
    'SOL/USDT:USDT'
    """
    return _normalize_symbol(exchange, symbol.upper(), market_type=market_type)


def from_exchange_symbol(native_symbol: str) -> str:
    """
    Convert an exchange-native symbol back to canonical uppercase form.

    Strips any ``/``, ``:`` separators and uppercases.

    Example
    -------
    >>> from_exchange_symbol("SOL/USDT:USDT")
    'SOLUSDT'
    """
    return native_symbol.replace("/", "").replace(":", "").upper()


def validate_symbol(exchange: str, symbol: str, exchange_instance) -> bool:
    """
    Check whether the given symbol exists in the exchange's loaded markets.

    Both the canonical (uppercase) form and the exchange-native form are
    tried.

    Parameters
    ----------
    exchange : str
        Exchange identifier (unused, kept for API consistency).
    symbol : str
        User-supplied symbol (e.g. ``"solusdt"``).
    exchange_instance : ccxt.Exchange
        An exchange object whose ``markets`` dict has been loaded.

    Returns
    -------
    bool
        ``True`` if the symbol is recognised.
    """
    markets = exchange_instance.markets
    canonical = normalize_symbol(symbol)
    if canonical in markets:
        return True
    # Try exchange-native format
    native = to_exchange_symbol(exchange, symbol)
    return native in markets

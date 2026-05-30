"""Tests for exchange symbol normalization helpers."""

from exchange.symbols import from_exchange_symbol, to_exchange_symbol
from exchange.mexc import MEXCExchange


def test_mexc_trb_perp_native_format():
    assert to_exchange_symbol("mexc", "TRBUSDT", market_type="perp") == "TRB/USDT:USDT"


def test_mexc_btc_perp_native_format():
    assert to_exchange_symbol("mexc", "BTCUSDT", market_type="perp") == "BTC/USDT:USDT"


def test_from_exchange_symbol_roundtrip():
    native = to_exchange_symbol("mexc", "TRBUSDT", market_type="perp")
    assert from_exchange_symbol(native) == "TRBUSDT"


def test_mexc_exchange_to_native_symbol():
    ex = MEXCExchange(config={})
    assert ex._to_native_symbol("TRBUSDT") == "TRB/USDT:USDT"
    assert ex._to_native_symbol("TRB/USDT:USDT") == "TRB/USDT:USDT"
    assert ex._to_canonical_symbol("TRB/USDT:USDT") == "TRBUSDT"

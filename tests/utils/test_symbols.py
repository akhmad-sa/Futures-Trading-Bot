from utils.symbols import canonical_symbol, parse_symbols


def test_canonical_symbol_compact():
    assert canonical_symbol("btcusdt") == "BTCUSDT"


def test_canonical_symbol_slash():
    assert canonical_symbol("BTC/USDT") == "BTCUSDT"


def test_canonical_symbol_perp():
    assert canonical_symbol("ETH/USDT:USDT") == "ETHUSDT"


def test_parse_symbols_comma_separated():
    assert parse_symbols("btcusdt,ethusdt,xrpusdt") == [
        "BTCUSDT",
        "ETHUSDT",
        "XRPUSDT",
    ]


def test_parse_symbols_space_separated():
    assert parse_symbols("BTCUSDT", "ETHUSDT") == ["BTCUSDT", "ETHUSDT"]


def test_parse_symbols_deduplicates():
    assert parse_symbols("BTCUSDT,btcusdt") == ["BTCUSDT"]

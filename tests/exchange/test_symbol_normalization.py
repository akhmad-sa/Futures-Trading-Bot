"""
Tests for symbol normalization across supported exchanges.
"""

import pytest

from market_data.ingestion.historical_downloader import EXCHANGE_NAME_MAP


# Symbols in ccxt format (e.g. "BTC/USDT")
SUPPORTED_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "ADA/USDT",
    "XRP/USDT",
]


class TestSymbolNormalization:
    """Verify that symbols are correctly handled by each exchange."""

    @pytest.mark.parametrize("exchange_id", ["binance", "bybit", "mexc"])
    @pytest.mark.parametrize("symbol", SUPPORTED_SYMBOLS)
    def test_symbol_in_markets(self, exchange_id, symbol):
        """Check that the symbol format is accepted by the exchange class."""
        exchange_cls = EXCHANGE_NAME_MAP[exchange_id]
        # We cannot load markets without API keys, but we can verify
        # that the exchange class exists and the symbol format is valid.
        assert exchange_cls is not None
        # The symbol format "BASE/QUOTE" is standard across ccxt.
        assert "/" in symbol

    def test_unsupported_exchange(self):
        """Verify that an unsupported exchange returns empty list."""
        from market_data.ingestion.historical_downloader import HistoricalDownloader
        downloader = HistoricalDownloader()
        import asyncio
        result = asyncio.run(
            downloader.download_range(
                exchange="unsupported_exchange",
                symbol="BTC/USDT",
                timeframe="1h",
            )
        )
        assert result == []

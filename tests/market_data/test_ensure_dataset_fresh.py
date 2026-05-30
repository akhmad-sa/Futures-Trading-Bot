import pytest

from market_data.models.candle import Candle
from market_data.services.market_data_service import MarketDataService
from market_data.dataset_sync import MS_PER_DAY


def _candle(ts: int) -> Candle:
    return Candle(
        timestamp=ts,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
    )


class TestEnsureDatasetFresh:
    @pytest.mark.asyncio
    async def test_stale_tail_triggers_download(self, tmp_path, monkeypatch):
        base = 1_700_000_000_000
        stale = [_candle(base), _candle(base + MS_PER_DAY)]
        service = MarketDataService(provider=[], data_dir=str(tmp_path / "candles"))
        await service.store_candles("mexc", "BTCUSDT", "15m", stale)

        new_candles = [_candle(base + 2 * MS_PER_DAY), _candle(base + 3 * MS_PER_DAY)]

        async def fake_download(exchange, symbol, timeframe, start_time, end_time):
            return new_candles

        monkeypatch.setattr(service, "_download_range", fake_download)
        monkeypatch.setattr(
            "market_data.dataset_sync.now_ms",
            lambda: base + int(3 * MS_PER_DAY),
        )

        info = await service.ensure_dataset_fresh(
            "mexc", "BTCUSDT", "15m", max_stale_days=1.0
        )
        assert info.count == 4
        loaded = await service.get_candles("mexc", "BTCUSDT", "15m")
        assert len(loaded) == 4

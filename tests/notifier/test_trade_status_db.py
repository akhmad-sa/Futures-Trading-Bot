import aiosqlite
import pytest

from notifier.trade_status import load_trade_report, format_trade_report


@pytest.mark.asyncio
async def test_load_trade_report_from_db(tmp_path):
    db = tmp_path / "trades.db"
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, side TEXT, entry_price REAL, exit_price REAL,
                quantity REAL, entry_time TEXT, exit_time TEXT, pnl REAL
            )
            """
        )
        await conn.execute(
            "INSERT INTO trades (symbol, side, pnl, exit_time) VALUES (?, ?, ?, ?)",
            ("DOGEUSDT", "long", 5.0, "2025-05-31T10:00:00+00:00"),
        )
        await conn.commit()

    report = await load_trade_report(db, recent_limit=5)
    msg = format_trade_report(report)
    assert "DOGEUSDT" in msg
    assert "+5.00" in msg

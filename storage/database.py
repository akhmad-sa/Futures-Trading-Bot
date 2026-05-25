"""
SQLite database for trade history using aiosqlite.
"""

import aiosqlite
from typing import Any


class TradeDatabase:
    """Persistent storage for completed trades."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open database and create tables if needed."""
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity REAL,
                entry_time TEXT,
                exit_time TEXT,
                pnl REAL
            )
            """
        )
        await self.conn.commit()

    async def save_trade(self, trade: dict[str, Any]) -> None:
        """Insert a completed trade record."""
        await self.conn.execute(
            """
            INSERT INTO trades (symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade["symbol"],
                trade["side"],
                trade["entry_price"],
                trade["exit_price"],
                trade["quantity"],
                trade.get("entry_time", ""),
                trade.get("exit_time", ""),
                trade["pnl"],
            ),
        )
        await self.conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            await self.conn.close()

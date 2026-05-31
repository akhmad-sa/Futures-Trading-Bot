"""
Telegram notification service using aiohttp.
"""

import aiohttp
import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send messages to a Telegram chat."""

    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send_message(self, text: str) -> bool:
        """Send a plain text message. Returns True on success."""
        if not self.is_configured:
            logger.warning("Telegram not configured (token/chat_id missing)")
            return False
        async with aiohttp.ClientSession() as session:
            payload = {"chat_id": self.chat_id, "text": text}
            async with session.post(
                f"{self.base_url}/sendMessage", json=payload
            ) as resp:
                if resp.status != 200:
                    logger.error("Telegram send failed: %s", await resp.text())
                    return False
                return True

    async def send_test(self) -> bool:
        """Send a test ping (used by the control bot /test command)."""
        return await self.send_message("🔔 Test notification — bot is reachable.")

    async def send_error(self, text: str) -> None:
        """Notify about an error."""
        await self.send_message(f"❌ Error: {text}")

    async def send_entry(self, symbol: str, side: str, size: float, price: float) -> None:
        """Notify about a new position entry."""
        await self.send_message(f"📈 Entry {side.upper()} {symbol}: size {size:.4f} @ {price:.2f}")

    async def send_exit(self, symbol: str, side: str, pnl: float) -> None:
        """Notify about a closed position with PnL."""
        emoji = "🟢" if pnl >= 0 else "🔴"
        await self.send_message(f"{emoji} Exit {symbol} ({side}): PnL {pnl:.2f}")

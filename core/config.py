"""
Centralised configuration loaded from .env using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppConfig(BaseSettings):
    """Application configuration with fields for exchange, notifier, risk, etc."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mexc_api_key: str = Field(default="", alias="MEXC_API_KEY")
    mexc_api_secret: str = Field(default="", alias="MEXC_API_SECRET")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    db_path: str = Field(default="storage/trade_history.db", alias="DB_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_concurrent_trades: int = Field(default=1, alias="MAX_CONCURRENT_TRADES")
    max_daily_loss: float = Field(default=500.0, alias="MAX_DAILY_LOSS")
    risk_per_trade: float = Field(default=0.02, alias="RISK_PER_TRADE")
    cooldown_seconds: int = Field(default=60, alias="COOLDOWN_SECONDS")
    symbols: list[str] = Field(default=["BTCUSDT"], alias="SYMBOLS")


def load_config() -> AppConfig:
    """Instantiate and return the app configuration."""
    return AppConfig()

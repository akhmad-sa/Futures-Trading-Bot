"""
Centralised configuration loaded from .env using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Any


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

    # Exchange selection
    exchange_name: str = Field(default="mexc", alias="EXCHANGE_NAME")
    # Multi‑account failover – list of dicts each with keys: api_key, api_secret
    exchange_accounts: list[dict[str, Any]] = Field(default=[], alias="EXCHANGE_ACCOUNTS")

    # New risk management fields
    max_drawdown_percent: float = Field(default=20.0, alias="MAX_DRAWDOWN_PERCENT")
    consecutive_loss_limit: int = Field(default=3, alias="CONSECUTIVE_LOSS_LIMIT")
    max_risk_per_symbol: float = Field(default=0.1, alias="MAX_RISK_PER_SYMBOL")
    max_leverage: int = Field(default=5, alias="MAX_LEVERAGE")
    stop_loss_atr_multiplier: float = Field(default=2.0, alias="STOP_LOSS_ATR_MULTIPLIER")

    # Multi‑strategy configuration
    strategies: list[dict[str, Any]] = Field(
        default=[
            {
                "name": "ExampleStrategy",
                "enabled": True,
                "symbols": ["BTCUSDT"],
                "params": {},
            }
        ],
        alias="STRATEGIES",
    )


def load_config() -> AppConfig:
    """Instantiate and return the app configuration."""
    return AppConfig()

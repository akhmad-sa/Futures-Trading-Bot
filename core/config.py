"""
Centralised configuration loaded from .env using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Any
import json


class AppConfig(BaseSettings):
    """Application configuration with fields for exchange, notifier, risk, etc."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Exchange API credentials
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    bybit_api_key: str = Field(default="", alias="BYBIT_API_KEY")
    bybit_api_secret: str = Field(default="", alias="BYBIT_API_SECRET")
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
    # Strategy execution timeframe (entries, retest, channel breakouts)
    timeframe: str = Field(default="1m", alias="TIMEFRAME")
    # Higher timeframe for HH/HL market structure bias (filter before entry)
    structure_timeframe: str = Field(default="1h", alias="STRUCTURE_TIMEFRAME")
    structure_mtf_enabled: bool = Field(default=True, alias="STRUCTURE_MTF_ENABLED")
    structure_pivot_len: int = Field(default=5, alias="STRUCTURE_PIVOT_LEN")
    structure_use_bos_choch: bool = Field(default=True, alias="STRUCTURE_USE_BOS_CHOCH")
    structure_break_confirm_close: bool = Field(
        default=True, alias="STRUCTURE_BREAK_CONFIRM_CLOSE"
    )
    structure_block_entry_on_counter_choch: bool = Field(
        default=True, alias="STRUCTURE_BLOCK_ENTRY_ON_COUNTER_CHOCH"
    )
    structure_choch_exit_enabled: bool = Field(
        default=False, alias="STRUCTURE_CHOCH_EXIT_ENABLED"
    )

    # Local candle storage (Parquet) — auto-sync before backtest if stale
    data_dir: str = Field(default="data/candles", alias="DATA_DIR")
    dataset_max_stale_days: float = Field(default=1.0, alias="DATASET_MAX_STALE_DAYS")
    dataset_sync_on_backtest: bool = Field(default=True, alias="DATASET_SYNC_ON_BACKTEST")

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

    # Global TP/SL (managed by RiskManager, not strategies)
    stop_loss_mode: str = Field(default="atr", alias="STOP_LOSS_MODE")
    stop_loss_pct: float = Field(default=0.015, alias="STOP_LOSS_PCT")
    take_profit_rr: float = Field(default=3.0, alias="TAKE_PROFIT_RR")
    min_sl_pct: float = Field(default=0.005, alias="MIN_SL_PCT")
    max_sl_pct: float = Field(default=0.018, alias="MAX_SL_PCT")
    min_sl_hold_bars: int = Field(default=2, alias="MIN_SL_HOLD_BARS")
    move_sl_to_breakeven_at_1r: bool = Field(default=True, alias="MOVE_SL_TO_BREAKEVEN_AT_1R")
    use_trend_exit: bool = Field(default=False, alias="USE_TREND_EXIT")
    trend_exit_after_1r_only: bool = Field(default=True, alias="TREND_EXIT_AFTER_1R_ONLY")
    partial_profit_enabled: bool = Field(default=False, alias="PARTIAL_PROFIT_ENABLED")
    partial_profit_pct: float = Field(default=50.0, alias="PARTIAL_PROFIT_PCT")
    partial_profit_at_r: float = Field(default=1.0, alias="PARTIAL_PROFIT_AT_R")
    stepped_trail_enabled: bool = Field(default=True, alias="STEPPED_TRAIL_ENABLED")
    stepped_trail_lock_offset: float = Field(default=2.0, alias="STEPPED_TRAIL_LOCK_OFFSET")

    # Portfolio compounding & martingale
    compounding_enabled: bool = Field(default=True, alias="COMPOUNDING_ENABLED")
    position_size_pct: float = Field(default=1.0, alias="POSITION_SIZE_PCT")
    martingale_enabled: bool = Field(default=False, alias="MARTINGALE_ENABLED")
    martingale_multiplier: float = Field(default=2.0, alias="MARTINGALE_MULTIPLIER")
    martingale_max_steps: int = Field(default=3, alias="MARTINGALE_MAX_STEPS")

    backtest_initial_capital: float = Field(default=10000.0, alias="BACKTEST_INITIAL_CAPITAL")
    backtest_halt_on_drawdown: bool = Field(default=False, alias="BACKTEST_HALT_ON_DRAWDOWN")
    portfolio_backtest: bool = Field(default=True, alias="PORTFOLIO_BACKTEST")
    min_signal_score: float = Field(default=70.0, alias="MIN_SIGNAL_SCORE")

    # Per-symbol strategy kwargs (JSON), merged over built-in alt defaults
    symbol_strategy_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="SYMBOL_STRATEGY_PARAMS"
    )

    @field_validator("symbol_strategy_params", mode="before")
    @classmethod
    def _parse_symbol_strategy_params(cls, v: Any) -> dict:
        if v is None or v == "":
            return {}
        if isinstance(v, str):
            return json.loads(v)
        return v

    # Multi‑strategy configuration
    default_strategy: str = Field(
        default="trendline_breakout", alias="DEFAULT_STRATEGY"
    )
    strategies: list[dict[str, Any]] = Field(
        default=[
            {
                "name": "trendline_breakout",
                "enabled": True,
                "symbols": ["BTCUSDT"],
                "params": {},
                "symbol_params": {},
            }
        ],
        alias="STRATEGIES",
    )


def load_config() -> AppConfig:
    """Instantiate and return the app configuration."""
    return AppConfig()

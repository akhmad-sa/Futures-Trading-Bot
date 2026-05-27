"""
Entry point for the trading bot.
Supports multiple exchanges via the exchange factory.
Can be launched in live, papertrade, backtest, or list mode.
"""

import asyncio
import argparse
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from core.config import load_config
from utils.logger import setup_logging
from exchange.exchange_factory import create_exchange
from execution.engine import ExecutionEngine
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from backtest.engine import BacktestEngine
from backtest.context import BacktestContext
from market_data import MarketDataService
from market_data.services.live_data_provider import LiveDataProvider

# ── Strategy registry (new) ───────────────────────────────────────
from strategy.registry import get_strategy, list_registered_strategies
from strategy.discovery import discover_and_register_strategies

# ── CLI discovery helpers ─────────────────────────────────────────
from scripts.discovery import (
    list_strategies,
    list_exchanges,
    get_available_strategy_names,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────


def parse_date(date_str: str) -> int:
    """Convert a YYYY-MM-DD string to a UTC millisecond timestamp."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.")


def resolve_strategy(config, strategy_name: Optional[str]) -> Optional[str]:
    """
    Resolve the strategy name to use.

    If *strategy_name* is provided, return it.
    Otherwise, try the configured default strategy.
    If that is not set, auto‑select the first discovered strategy.
    Returns ``None`` if no strategy can be resolved.
    """
    if strategy_name:
        return strategy_name

    # Try configured default
    default = getattr(config, "default_strategy", None)
    if default:
        print(f"Using configured default strategy: {default}")
        return default

    # Auto‑discover using metadata names
    available = get_available_strategy_names()
    if available:
        first = available[0]
        print(f"Auto‑selected strategy: {first}")
        return first

    return None


def load_strategies_from_config(config) -> List[Any]:
    """
    Load strategy instances from the config's 'strategies' list.

    Each entry should have a 'name' field that matches a registered
    strategy metadata name.  Missing or invalid strategies are logged
    and skipped.
    """
    discovered = discover_and_register_strategies()
    if not discovered:
        logger.warning("No strategies discovered.")
        return []

    cfg_strategies = getattr(config, "strategies", [])
    instances: List[Any] = []

    for entry in cfg_strategies:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if not name:
            logger.warning("Strategy config entry missing 'name': %s", entry)
            continue
        try:
            cls = get_strategy(name)
        except KeyError:
            logger.warning(
                "Strategy '%s' configured but not registered; available: %s",
                name,
                list_registered_strategies().keys(),
            )
            continue
        params = entry.get("params", {}) if isinstance(entry, dict) else {}
        try:
            instance = cls(config=config, symbols=getattr(config, "symbols", []), enabled=True, **params)
            instances.append(instance)
        except Exception as e:
            logger.error("Failed to instantiate strategy '%s': %s", name, e)
    return instances


# ── Mode handlers ─────────────────────────────────────────────────


async def run_live_trading(config, exchange_name: str, mode: str, strategy_filter: Optional[str]):
    """Run the bot in live or paper trading mode."""
    db = TradeDatabase(config.db_path)
    await db.open()

    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
    risk_manager = RiskManager(config)

    exchange_cfg = {
        "api_key": getattr(config, f"{exchange_name}_api_key", ""),
        "api_secret": getattr(config, f"{exchange_name}_api_secret", ""),
    }
    if mode == "papertrade":
        exchange_cfg["testnet"] = True

    exchange = create_exchange(exchange_name, exchange_cfg)
    await exchange.connect()

    # Load strategies from config using the global registry
    strategies = load_strategies_from_config(config)

    if strategy_filter:
        strategies = [s for s in strategies if getattr(s, 'name', '') == strategy_filter]
        if not strategies:
            logger.error("Strategy '%s' not found among loaded instances.", strategy_filter)
            return

    engine = ExecutionEngine(
        exchange,
        risk_manager,
        db,
        notifier,
        symbols=config.symbols,
    )

    logger.info("Starting execution engine in %s mode for %s...", mode, exchange_name)
    await engine.start(strategies)


async def run_backtest(config, strategy_name: str, symbols: List[str], exchange: str,
                       start_time: Optional[int] = None,
                       end_time: Optional[int] = None):
    """Run a backtest for a single strategy over given symbols."""
    # 1. Ensure the global registry is populated
    discovered = discover_and_register_strategies()
    if not discovered:
        logger.error("No strategies discovered.")
        return

    # 2. Look up the strategy class
    try:
        strategy_class = get_strategy(strategy_name)
    except KeyError:
        logger.error(
            "Strategy '%s' not registered. Available: %s",
            strategy_name,
            list(discovered.keys()),
        )
        return

    # 3. Find strategy-specific config params (if any)
    cfg_strategies = getattr(config, "strategies", [])
    strategy_config = next(
        (s for s in cfg_strategies if (isinstance(s, dict) and s.get("name") == strategy_name)),
        {},
    )
    params = strategy_config.get("params", {}) if isinstance(strategy_config, dict) else {}
    try:
        strategy = strategy_class(
            config=config, symbols=symbols, enabled=True, **params
        )
    except Exception as e:
        logger.error("Failed to instantiate strategy '%s': %s", strategy_name, e)
        return

    # 4. Initialize components
    risk_manager = RiskManager(config)
    engine = BacktestEngine(
        risk_manager=risk_manager,
        initial_capital=getattr(config, 'backtest_initial_capital', 10000.0),
        commission=getattr(config, 'exchange_commission', 0.001),
        slippage=getattr(config, 'backtest_slippage', 0.001),
        funding_rate=getattr(config, 'backtest_funding_rate', 0.0),
    )

    # 5. Create market data service with a live provider
    market_data_service = MarketDataService(
        provider=LiveDataProvider(),
    )

    # 6. Create backtest context
    context = BacktestContext(start_time=start_time, end_time=end_time)
    logger.info("Backtest period: %s", context)

    # 7. Run backtest for each symbol
    for symbol in symbols:
        logger.info("--- Running Backtest for %s on %s ---", strategy_name, symbol)
        report = await engine.run(
            service=market_data_service,
            strategy=strategy,
            symbol=symbol,
            timeframe=config.timeframe,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
        )
        # Display report
        print("\n--- Backtest Report ---")
        print(f"Initial Capital: {report.initial_capital:.2f}")
        print(f"Final Capital:   {report.final_capital:.2f}")
        print(f"Total PnL:       {report.total_pnl:.2f}")
        print(f"Total Funding:   {report.total_funding_fees:.2f}")
        print(f"Metrics:         {report.metrics}")
        print("-----------------------\n")


# ── Entry point ───────────────────────────────────────────────────


async def main() -> None:
    """Initialize all components and start the bot."""
    parser = argparse.ArgumentParser(
        description="Trading Bot – multi‑exchange, multi‑strategy trading and backtesting."
    )
    parser.add_argument(
        "-m", "--mode", default="live",
        choices=["live", "papertrade", "backtest", "list"],
        help="Trading mode (default: live). Use 'list' to discover available strategies/exchanges."
    )
    parser.add_argument(
        "--what", type=str, choices=["strategies", "exchanges"],
        help="When --mode list, specify what to list (strategies or exchanges)."
    )
    parser.add_argument(
        "-e", "--exchange", type=str,
        help="Exchange to use (overrides config)."
    )
    parser.add_argument(
        "-s", "--strategy", type=str,
        help="Strategy to run. If omitted, uses default or first discovered strategy."
    )
    parser.add_argument(
        "--symbol", type=str,
        help="Single symbol to trade (e.g., BTC/USDT)."
    )
    parser.add_argument(
        "--symbols", type=str, nargs="+",
        help="Space‑separated list of symbols (e.g. --symbols BTC/USDT ETH/USDT)."
    )
    parser.add_argument(
        "--timeframe", type=str,
        help="Timeframe to use (e.g., 1m, 5m, 1h)."
    )
    parser.add_argument(
        "--start", type=str,
        help="Backtest start date (YYYY-MM-DD). If omitted, uses earliest available data."
    )
    parser.add_argument(
        "--end", type=str,
        help="Backtest end date (YYYY-MM-DD). If omitted, uses latest available data."
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # List mode
    # ------------------------------------------------------------------
    if args.mode == "list":
        if args.what == "strategies":
            names = get_available_strategy_names()
            print("Available strategies:")
            for name in names:
                print(f"  {name}")
        elif args.what == "exchanges":
            exchanges = list_exchanges()
            print("Available exchange adapters:")
            for e in exchanges:
                print(f"  {e}")
        else:
            print("Usage: python main.py --mode list --what [strategies|exchanges]")
        return

    # ------------------------------------------------------------------
    # Normal modes
    # ------------------------------------------------------------------
    config = load_config()
    setup_logging(config.log_level)

    exchange_name = args.exchange or config.exchange_name

    # ------------------------------------------------------------------
    # Resolve strategy (after defaults)
    # ------------------------------------------------------------------
    strategy_name = resolve_strategy(config, args.strategy)

    # Log the registered strategies at startup for transparency
    if logger.isEnabledFor(logging.DEBUG):
        registry = list_registered_strategies()
        logger.debug("Registered strategies: %s", list(registry.keys()))

    if args.mode == "backtest":
        if not strategy_name:
            print("Error: No strategy available. Use --strategy or configure a default.")
            print("Available strategies:")
            for s in get_available_strategy_names():
                print(f"  {s}")
            return

        # Determine symbols
        if args.symbols:
            symbols = args.symbols
        elif args.symbol:
            symbols = [args.symbol]
        else:
            default_symbols = getattr(config, "symbols", None)
            if default_symbols:
                symbols = default_symbols
            else:
                print("Error: No symbols provided. Use --symbol or --symbols.")
                return

        # Parse optional date range
        start_time = None
        end_time = None
        if args.start:
            start_time = parse_date(args.start)
        if args.end:
            end_time = parse_date(args.end)

        await run_backtest(config, strategy_name, symbols, exchange_name,
                           start_time=start_time, end_time=end_time)
    else:
        # Live / papertrade mode
        if not strategy_name:
            logger.warning("No strategy specified. Running without strategy filter.")
        await run_live_trading(config, exchange_name, args.mode, strategy_name)


if __name__ == "__main__":
    asyncio.run(main())

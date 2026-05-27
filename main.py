"""
Entry point for the trading bot.
Supports multiple exchanges via the exchange factory.
Can be launched in live, papertrade, backtest, or list mode.
"""

import asyncio
import argparse
from datetime import datetime, timezone
from typing import List, Optional

from core.config import load_config
from utils.logger import setup_logging
from strategy.registry import StrategyRegistry
from exchange.exchange_factory import create_exchange
from execution.engine import ExecutionEngine
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from backtest.engine import BacktestEngine
from backtest.context import BacktestContext
from market_data import MarketDataService
from market_data.services.live_data_provider import LiveDataProvider
from scripts.discovery import list_strategies, list_exchanges


def parse_date(date_str: str) -> int:
    """Convert a YYYY-MM-DD string to a UTC millisecond timestamp."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.")


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

    registry = StrategyRegistry()
    strategies = registry.load_from_config(config)

    if strategy_filter:
        strategies = [s for s in strategies if getattr(s, 'name', '') == strategy_filter]
        if not strategies:
            print(f"Error: Strategy '{strategy_filter}' not found or loaded.")
            return

    engine = ExecutionEngine(
        exchange,
        risk_manager,
        db,
        notifier,
        symbols=config.symbols,
    )

    print(f"Starting execution engine in {mode} mode for {exchange_name}...")
    await engine.start(strategies)


async def run_backtest(config, strategy_name: str, symbols: List[str], exchange: str,
                       start_time: Optional[int] = None,
                       end_time: Optional[int] = None):
    """Run a backtest for a single strategy over given symbols."""
    # 1. Load strategy
    registry = StrategyRegistry()
    try:
        strategy_class = registry.get(strategy_name)
        strategy_config = next(
            (s for s in config.strategies if s.get("name") == strategy_name), {}
        )
        params = strategy_config.get("params", {})
        strategy = strategy_class(
            config=config, symbols=symbols, enabled=True, **params
        )
    except KeyError:
        print(f"Error: Strategy '{strategy_name}' not registered or could not be loaded.")
        return

    # 2. Initialize components
    risk_manager = RiskManager(config)
    engine = BacktestEngine(
        risk_manager=risk_manager,
        initial_capital=getattr(config, 'backtest_initial_capital', 10000.0),
        commission=getattr(config, 'exchange_commission', 0.001),
        slippage=getattr(config, 'backtest_slippage', 0.001),
        funding_rate=getattr(config, 'backtest_funding_rate', 0.0),
    )

    # 3. Create market data service with a live provider
    market_data_service = MarketDataService(
        provider=LiveDataProvider(),
    )

    # 4. Create backtest context
    context = BacktestContext(start_time=start_time, end_time=end_time)
    print(f"Backtest period: {context}")

    # 5. Run backtest for each symbol
    for symbol in symbols:
        print(f"\n--- Running Backtest for {strategy_name} on {symbol} ---")
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
        help="Strategy to run. Required for backtest mode."
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
            strategies = list_strategies()
            print("Available strategies:")
            for s in strategies:
                print(f"  {s}")
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

    if args.mode == "backtest":
        if not args.strategy:
            parser.error("--strategy is required for backtest mode.")

        # Determine symbols
        if args.symbols:
            symbols = args.symbols
        elif args.symbol:
            symbols = [args.symbol]
        else:
            parser.error("--symbol or --symbols is required for backtest mode.")

        # Parse optional date range
        start_time = None
        end_time = None
        if args.start:
            start_time = parse_date(args.start)
        if args.end:
            end_time = parse_date(args.end)

        await run_backtest(config, args.strategy, symbols, exchange_name,
                           start_time=start_time, end_time=end_time)
    else:
        await run_live_trading(config, exchange_name, args.mode, args.strategy)


if __name__ == "__main__":
    asyncio.run(main())

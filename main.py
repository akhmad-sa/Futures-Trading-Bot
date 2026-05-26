"""
Entry point for the trading bot.
Supports multiple exchanges via the exchange factory.
Can be launched in live, papertrade, or backtest mode.
"""

import asyncio
import argparse
from typing import Optional

from core.config import load_config
from utils.logger import setup_logging
from strategy.registry import StrategyRegistry
from exchange.exchange_factory import create_exchange
from execution.engine import ExecutionEngine
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from backtest.engine import BacktestEngine


async def run_live_trading(config, exchange_name: str, mode: str, strategy_filter: Optional[str]):
    """Run the bot in live or paper trading mode."""
    db = TradeDatabase(config.db_path)
    await db.open()

    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
    risk_manager = RiskManager(config)

    # Build exchange configuration dict using the selected exchange's env vars
    exchange_cfg = {
        "api_key": getattr(config, f"{exchange_name}_api_key", ""),
        "api_secret": getattr(config, f"{exchange_name}_api_secret", ""),
    }
    if mode == "papertrade":
        exchange_cfg["testnet"] = True

    exchange = create_exchange(exchange_name, exchange_cfg)
    await exchange.connect()

    # Load strategies dynamically from config
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


async def run_backtest(config, strategy_name: str, symbol: str):
    """Run a backtest for a single strategy and symbol."""
    print(f"--- Running Backtest for {strategy_name} on {symbol} ---")

    # 1. Load historical data (Not implemented)
    # TODO: Implement data loading logic (e.g., from a file or database)
    print("Historical data loading is not implemented. Using empty dataset.")
    ohlcv = []
    if not ohlcv:
        print("Warning: No historical data loaded. Backtest will be empty.")

    # 2. Load strategy
    registry = StrategyRegistry()
    try:
        strategy_class = registry.get(strategy_name)
        # Find strategy-specific params from config if they exist
        strategy_config = next(
            (s for s in config.strategies if s.get("name") == strategy_name), {}
        )
        params = strategy_config.get("params", {})
        strategy = strategy_class(
            config=config, symbols=[symbol], enabled=True, **params
        )
    except KeyError:
        print(f"Error: Strategy '{strategy_name}' not registered or could not be loaded.")
        return

    # 3. Initialize components
    risk_manager = RiskManager(config)
    engine = BacktestEngine(
        risk_manager=risk_manager,
        initial_capital=getattr(config, 'backtest_initial_capital', 10000.0),
        commission=getattr(config, 'exchange_commission', 0.001),
        slippage=getattr(config, 'backtest_slippage', 0.001),
        funding_rate=getattr(config, 'backtest_funding_rate', 0.0),
    )

    # 4. Run backtest
    report = await engine.run(ohlcv, strategy, symbol)

    # 5. Display report
    print("\n--- Backtest Report ---")
    print(f"Initial Capital: {report.initial_capital:.2f}")
    print(f"Final Capital:   {report.final_capital:.2f}")
    print(f"Total PnL:       {report.total_pnl:.2f}")
    print(f"Total Funding:   {report.total_funding_fees:.2f}")
    print(f"Metrics:         {report.metrics}")
    print("-----------------------\n")


async def main() -> None:
    """Initialize all components and start the bot."""
    parser = argparse.ArgumentParser(description="Trading Bot")
    parser.add_argument(
        "-m", "--mode", default="live", choices=["live", "papertrade", "backtest"],
        help="Trading mode (default: live)."
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
        "--symbol", type=str, help="Symbol to trade (e.g., BTC/USDT)."
    )
    parser.add_argument(
        "--timeframe", type=str, help="Timeframe to use (e.g., 1m, 5m, 1h)."
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(config.log_level)

    exchange_name = args.exchange or config.exchange_name

    if args.mode == "backtest":
        if not args.strategy:
            parser.error("--strategy is required for backtest mode.")
        if not args.symbol:
            parser.error("--symbol is required for backtest mode.")
        await run_backtest(config, args.strategy, args.symbol)
    else:
        await run_live_trading(config, exchange_name, args.mode, args.strategy)


if __name__ == "__main__":
    asyncio.run(main())

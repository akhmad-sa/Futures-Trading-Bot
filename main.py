"""
Futures Trading Bot — entry point.

Supports multiple perpetual-futures exchanges via the exchange factory.
Modes: live, papertrade, backtest, list.
"""

import asyncio
import argparse
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from core.config import load_config
from core.project import PROJECT_NAME, VERSION
from utils.logger import setup_logging
from utils import console as term
from utils.symbols import parse_symbols
from exchange.exchange_factory import create_exchange
from execution.live_engine import LivePortfolioEngine
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from backtest.engine import BacktestEngine, RiskConfig
from backtest.context import BacktestContext
from market_data import MarketDataService
from market_data.services.live_data_provider import LiveDataProvider
from market_structure.mtf import MultiTimeframeConfig
from market_structure.event_log import StructureEventLogger

# ── Strategy registry (new) ───────────────────────────────────────
from strategy.registry import get_strategy, list_registered_strategies
from strategy.discovery import discover_and_register_strategies
from strategy.symbol_params import (
    resolve_strategy_params,
    list_symbols_for_strategy_entry,
)

# ── CLI discovery helpers ─────────────────────────────────────────
from scripts.discovery import (
    list_strategies,
    list_exchanges,
    get_available_strategy_names,
)

# ── Simulation configuration ──────────────────────────────────────
from simulation.config import SimulationConfig

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
        logger.info("Using configured default strategy: %s", default)
        return default

    # Auto‑discover using metadata names
    available = get_available_strategy_names()
    if available:
        first = available[0]
        logger.info("Auto-selected strategy: %s", first)
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
        if not isinstance(entry, dict):
            continue
        enabled = entry.get("enabled", True)
        symbols = list_symbols_for_strategy_entry(entry, config)
        for symbol in symbols:
            sym_params = resolve_strategy_params(
                name,
                symbol,
                global_params=params,
                strategy_entry=entry,
                config=config,
            )
            try:
                instance = cls(
                    config=config,
                    symbols=[symbol],
                    enabled=enabled,
                    **sym_params,
                )
                instances.append(instance)
            except Exception as e:
                logger.error(
                    "Failed to instantiate strategy '%s' for %s: %s",
                    name,
                    symbol,
                    e,
                )
    return instances


# ── Mode handlers ─────────────────────────────────────────────────


def _resolve_live_symbols(config, args) -> List[str]:
    if args.symbols:
        return parse_symbols(*args.symbols)
    if args.symbol:
        return parse_symbols(args.symbol)
    cfg_symbols = getattr(config, "symbols", None) or []
    return parse_symbols(*cfg_symbols) if cfg_symbols else []


def _build_strategy_instances(
    config,
    strategy_name: str,
    symbols: List[str],
) -> dict[str, Any]:
    """One strategy instance per symbol (portfolio / live)."""
    discover_and_register_strategies()
    strategy_class = get_strategy(strategy_name)
    cfg_strategies = getattr(config, "strategies", [])
    strategy_entry = next(
        (s for s in cfg_strategies if isinstance(s, dict) and s.get("name") == strategy_name),
        {},
    )
    global_params = strategy_entry.get("params", {}) if isinstance(strategy_entry, dict) else {}
    instances: dict[str, Any] = {}
    for symbol in symbols:
        sym_params = resolve_strategy_params(
            strategy_name,
            symbol,
            global_params=global_params,
            strategy_entry=strategy_entry,
            config=config,
        )
        instances[symbol] = strategy_class(
            config=config,
            symbols=[symbol],
            enabled=True,
            **sym_params,
        )
    return instances


async def run_live_trading(
    config,
    exchange_name: str,
    mode: str,
    strategy_name: Optional[str],
    symbols: List[str],
):
    """Run portfolio-style live or paper trading (closed-bar, MTF, risk exits)."""
    if not strategy_name:
        logger.error("No strategy resolved for live/paper mode.")
        return
    if not symbols:
        logger.error("No symbols configured. Use SYMBOLS or --symbol/--symbols.")
        return

    db = TradeDatabase(config.db_path)
    await db.open()

    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
    risk_manager = RiskManager(config)

    exchange_cfg = {
        "api_key": getattr(config, f"{exchange_name}_api_key", ""),
        "api_secret": getattr(config, f"{exchange_name}_api_secret", ""),
    }
    if mode == "papertrade":
        # Simulated fills when venue has no ccxt testnet; live OHLCV from REST.
        exchange_cfg["paper_simulate"] = True
        exchange_cfg["paper_initial_balance"] = float(
            getattr(config, "backtest_initial_capital", 10_000.0)
        )

    exchange = create_exchange(exchange_name, exchange_cfg)
    await exchange.connect()

    try:
        strategies_map = _build_strategy_instances(config, strategy_name, symbols)
    except KeyError:
        logger.error(
            "Strategy '%s' not registered. Available: %s",
            strategy_name,
            list_registered_strategies().keys(),
        )
        return

    if not strategies_map:
        logger.error("No strategy instances created for live trading.")
        return

    engine = LivePortfolioEngine(
        exchange,
        risk_manager,
        db,
        notifier,
        config,
        mode=mode,
    )
    logger.info(
        "Starting %s portfolio engine on %s (%s)",
        mode,
        exchange_name,
        ", ".join(strategies_map.keys()),
    )
    try:
        await engine.start(strategies_map, list(strategies_map.keys()))
    finally:
        await engine.stop()
        await exchange.disconnect()
        await db.close()


async def sync_backtest_datasets(
    service: MarketDataService,
    config: Any,
    symbols: List[str],
    exchange: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> None:
    """Audit local Parquet datasets and append candles if older than threshold."""
    if not getattr(config, "dataset_sync_on_backtest", True):
        logger.info("Dataset sync on backtest disabled (DATASET_SYNC_ON_BACKTEST=false)")
        return

    max_stale = float(getattr(config, "dataset_max_stale_days", 1.0))
    mtf_config = MultiTimeframeConfig.resolve(config)
    timeframes: set[str] = {getattr(config, "timeframe", "15m")}
    if mtf_config.is_active:
        timeframes.add(mtf_config.strategy_timeframe)
        timeframes.add(mtf_config.structure_timeframe)

    print("\n=== DATASET SYNC ===", flush=True)
    print(
        f"Checking local data (max stale {max_stale:.1f} day) for "
        f"{', '.join(symbols)} | TFs: {', '.join(sorted(timeframes))}",
        flush=True,
    )

    for symbol in symbols:
        for tf in sorted(timeframes):
            await service.ensure_dataset_fresh(
                exchange,
                symbol,
                tf,
                max_stale_days=max_stale,
                start_time=start_time,
                end_time=end_time,
            )
    print("", flush=True)


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
    global_params = strategy_config.get("params", {}) if isinstance(strategy_config, dict) else {}

    # 4. Initialize components
    risk_manager = RiskManager(config)

    # Build simulation config from config values (or use defaults)
    sim_cfg = SimulationConfig(
        maker_fee=getattr(config, 'exchange_maker_fee', 0.001),
        taker_fee=getattr(config, 'exchange_taker_fee', 0.001),
        slippage_bps=getattr(config, 'backtest_slippage_bps', 10),
        funding_rate=getattr(config, 'backtest_funding_rate', 0.0),
        funding_enabled=getattr(config, 'backtest_funding_enabled', True),
        funding_interval_hours=getattr(config, 'backtest_funding_interval_hours', 8),
    )

    logger.info(
        "Simulation config: maker_fee=%s, taker_fee=%s, slippage_bps=%s, "
        "funding_rate=%s, funding_enabled=%s, funding_interval_hours=%s",
        sim_cfg.maker_fee, sim_cfg.taker_fee, sim_cfg.slippage_bps,
        sim_cfg.funding_rate, sim_cfg.funding_enabled, sim_cfg.funding_interval_hours,
    )

    engine = BacktestEngine(
        risk_manager=risk_manager,
        initial_capital=getattr(config, "backtest_initial_capital", 10000.0),
        risk_config=RiskConfig.from_app_config(config),
        simulation_config=sim_cfg,
    )

    # 5. Create market data service with a live provider
    market_data_service = MarketDataService(
        provider=LiveDataProvider(),
        data_dir=getattr(config, "data_dir", "data/candles"),
    )

    await sync_backtest_datasets(
        market_data_service,
        config,
        symbols,
        exchange,
        start_time=start_time,
        end_time=end_time,
    )

    # 6. Create backtest context
    context = BacktestContext(start_time=start_time, end_time=end_time)
    logger.info("Backtest period: %s", context)

    mtf_config = MultiTimeframeConfig.resolve(config)
    if mtf_config.is_active:
        logger.info(
            "Multi-timeframe: strategy=%s structure=%s",
            mtf_config.strategy_timeframe,
            mtf_config.structure_timeframe,
        )
    structure_pivot_len = int(getattr(config, "structure_pivot_len", 5))
    mtf_kwargs = {
        "mtf_config": mtf_config,
        "structure_pivot_len": structure_pivot_len,
        "structure_use_bos_choch": bool(getattr(config, "structure_use_bos_choch", True)),
        "structure_break_confirm_close": bool(
            getattr(config, "structure_break_confirm_close", True)
        ),
    }

    # 7. Backtest — portfolio (shared capital) or per-symbol
    initial_capital = getattr(config, "backtest_initial_capital", 10000.0)
    use_portfolio = len(symbols) > 1 and getattr(config, "portfolio_backtest", True)

    if use_portfolio and hasattr(engine, "run_portfolio"):
        strategies_map: dict[str, Any] = {}
        for symbol in symbols:
            sym_params = resolve_strategy_params(
                strategy_name,
                symbol,
                global_params=global_params,
                strategy_entry=strategy_config if isinstance(strategy_config, dict) else {},
                config=config,
            )
            try:
                strategies_map[symbol] = strategy_class(
                    config=config, symbols=[symbol], enabled=True, **sym_params
                )
            except Exception as e:
                logger.error("Failed to instantiate strategy for %s: %s", symbol, e)

        if not strategies_map:
            logger.error("No strategies instantiated for portfolio backtest.")
            return

        logger.info(
            "--- Portfolio backtest %s on %s ---",
            strategy_name,
            ", ".join(strategies_map.keys()),
        )
        portfolio_max = len(strategies_map)
        if not getattr(config, "portfolio_max_concurrent_symbols", True):
            portfolio_max = int(getattr(config, "max_concurrent_trades", 1))
        structure_logger = StructureEventLogger.from_config(config)
        report = await engine.run_portfolio(
            service=market_data_service,
            strategies=strategies_map,
            symbols=list(strategies_map.keys()),
            timeframe=config.timeframe,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            max_concurrent_trades=portfolio_max,
            structure_logger=structure_logger,
            **mtf_kwargs,
        )
        logger.info(
            "Portfolio exit summary: TP=%d SL=%d trend=%d trades=%d",
            report.exit_summary.take_profit,
            report.exit_summary.stop_loss,
            report.exit_summary.trend_exit,
            len(report.trades),
        )
        term.backtest_report(
            report.initial_capital,
            report.final_capital,
            report.total_pnl,
            report.total_funding_fees,
            report.metrics,
            report.exit_summary,
        )
        return

    combined_pnl = 0.0
    combined_trades = 0

    for symbol in symbols:
        sym_params = resolve_strategy_params(
            strategy_name,
            symbol,
            global_params=global_params,
            strategy_entry=strategy_config if isinstance(strategy_config, dict) else {},
            config=config,
        )
        try:
            strategy = strategy_class(
                config=config, symbols=[symbol], enabled=True, **sym_params
            )
        except Exception as e:
            logger.error("Failed to instantiate strategy for %s: %s", symbol, e)
            continue

        logger.info("--- Running Backtest for %s on %s ---", strategy_name, symbol)
        term.print_symbol_header(symbol, sym_params)
        report = await engine.run(
            service=market_data_service,
            strategy=strategy,
            symbol=symbol,
            timeframe=config.timeframe,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            **mtf_kwargs,
        )
        combined_pnl += report.total_pnl
        combined_trades += len(report.trades)
        logger.info(
            "Exit summary: TP=%d (%.2f) SL=%d (%.2f) trend=%d (%.2f) "
            "max_dd=%d (%.2f) other=%d (%.2f)",
            report.exit_summary.take_profit,
            report.exit_summary.take_profit_pnl,
            report.exit_summary.stop_loss,
            report.exit_summary.stop_loss_pnl,
            report.exit_summary.trend_exit,
            report.exit_summary.trend_exit_pnl,
            report.exit_summary.max_drawdown,
            report.exit_summary.max_drawdown_pnl,
            report.exit_summary.other,
            report.exit_summary.other_pnl,
        )
        term.backtest_report(
            report.initial_capital,
            report.final_capital,
            report.total_pnl,
            report.total_funding_fees,
            report.metrics,
            report.exit_summary,
        )

    if len(symbols) > 1:
        term.multi_symbol_summary(symbols, initial_capital, combined_pnl, combined_trades)


# ── Entry point ───────────────────────────────────────────────────


async def main() -> None:
    """Initialize all components and start the bot."""
    parser = argparse.ArgumentParser(
        description="Futures Trading Bot — multi-exchange perpetual futures trading and backtesting.",
        prog=PROJECT_NAME,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROJECT_NAME} {VERSION}",
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
        help="Symbol(s) to trade. One symbol or comma-separated (e.g. BTCUSDT or BTCUSDT,ETHUSDT)."
    )
    parser.add_argument(
        "--symbols", type=str, nargs="+",
        help="Space-separated symbols (e.g. --symbols BTCUSDT ETHUSDT XRPUSDT)."
    )
    parser.add_argument(
        "--timeframe", type=str,
        help="Strategy timeframe (entries, e.g. 5m, 15m). Overrides TIMEFRAME.",
    )
    parser.add_argument(
        "--structure-timeframe", type=str,
        help="Market structure timeframe (bias filter, e.g. 1h, 4h). Overrides STRUCTURE_TIMEFRAME.",
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

    if args.timeframe:
        config.timeframe = args.timeframe
    if args.structure_timeframe:
        config.structure_timeframe = args.structure_timeframe

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

        # Determine symbols (comma or space separated)
        if args.symbols:
            symbols = parse_symbols(*args.symbols)
        elif args.symbol:
            symbols = parse_symbols(args.symbol)
        else:
            default_symbols = getattr(config, "symbols", None)
            if default_symbols:
                symbols = parse_symbols(*default_symbols)
            else:
                print("Error: No symbols provided. Use --symbol or --symbols.")
                print("  Single:   --symbol BTCUSDT")
                print("  Multiple: --symbol BTCUSDT,ETHUSDT,XRPUSDT")
                print("            --symbols BTCUSDT ETHUSDT XRPUSDT")
                return

        if not symbols:
            print("Error: No valid symbols after parsing.")
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
        if not strategy_name:
            print("Error: No strategy available. Use --strategy or DEFAULT_STRATEGY.")
            return
        live_symbols = _resolve_live_symbols(config, args)
        if not live_symbols:
            print("Error: No symbols. Set SYMBOLS in configs/strategy.env or use --symbols.")
            return
        await run_live_trading(
            config, exchange_name, args.mode, strategy_name, live_symbols
        )


if __name__ == "__main__":
    asyncio.run(main())

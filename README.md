# MEXC Futures Trading Bot – Production‑Grade Starter

A modular, async‑first trading bot for MEXC Futures (perpetual swaps) built with Python 3.12.

## Features
- Real‑time ticker/order updates via WebSocket
- REST API integration using `ccxt`
- Pluggable strategies (example: EMA crossover + RSI filter + volume confirmation)
- Risk management (max daily loss, max concurrent trades, cooldown)
- Persistent trade history (SQLite)
- Telegram notifications for entries, exits, errors, PnL
- Lightweight backtesting engine with performance metrics
- Portfolio backtest and **paper trade** with the same engine path (MTF structure, scored picks, global risk exits)

## Quick start

### Backtest (portfolio, same as your `output.log` run)

```bash
python main.py -m backtest -s trendline_breakout --symbols BTCUSDT TRBUSDT DOGEUSDT
```

Tune modular env under `configs/` (`strategy.env`, `risk.env`, `market_structure.env`).

### Paper trade (MEXC testnet)

1. Put API keys in root `.env` (`MEXC_API_KEY`, `MEXC_API_SECRET`).
2. Set symbols in `configs/strategy.env` (e.g. `TRBUSDT`, `DOGEUSDT`).
3. Run:

```bash
python main.py -m papertrade -s trendline_breakout --symbols TRBUSDT DOGEUSDT
```

Paper mode **simulates** orders (no MEXC testnet in ccxt) using live OHLCV and a virtual balance (`BACKTEST_INITIAL_CAPITAL`). The live engine polls closed bars on `TIMEFRAME`, applies HTF structure, scans `evaluate_prospect`, and manages SL/partial/trail like backtest.

### Live

Same command with `-m live` (real funds — use only after paper validation).

### Add another strategy

1. Implement under `strategy/implementations/your_strategy.py` (subclass `BaseStrategy`, set `name`).
2. Register via discovery (`strategy/discovery.py` picks up the module).
3. Add to `STRATEGIES` in `configs/strategy.env` or pass `-s your_strategy`.

## Project Structure

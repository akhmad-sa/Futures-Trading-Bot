# Futures Trading Bot

A modular, async-first bot for **perpetual futures** across multiple exchanges. Built with Python 3.12.

**Default exchange today:** MEXC (`EXCHANGE_NAME=mexc`). The architecture is exchange-agnostic — adapters live under `exchange/` (MEXC, Binance, Bybit via factory).

## Features

- Multi-exchange REST + WebSocket via `ccxt` and pluggable adapters
- Market structure on higher TF (HH/HL, BOS/CHoCH) with global MTF config
- Pluggable strategies (e.g. trendline breakout with signal scoring)
- Risk management: SL/TP, partial profit, stepped trailing SL, portfolio slots
- Persistent trade history (SQLite)
- Telegram notifications for entries, exits, errors, PnL
- Backtest, portfolio replay, and **paper trade** on the same engine path
- Local Parquet candle storage with optional auto-sync before backtest

## Supported exchanges

| Exchange | Adapter | Status |
|----------|---------|--------|
| MEXC | `exchange/mexc.py` | Primary — live, paper, backtest |
| Binance | `exchange/binance.py` | Adapter stub / expand as needed |
| Bybit | `exchange/bybit.py` | Adapter stub / expand as needed |

Set active exchange in `configs/exchange.env`:

```env
EXCHANGE_NAME=mexc
```

API keys for each venue go in root `.env` (see `.env.example`).

## Quick start

### Backtest (portfolio)

```bash
python main.py -m backtest -s trendline_breakout --symbols BTCUSDT TRBUSDT DOGEUSDT
```

Tune modular env under `configs/` (`strategy.env`, `risk.env`, `market_structure.env`).

Use `-e bybit` or `-e binance` when those adapters are fully wired for your workflow.

### Paper trade

1. Put API keys in root `.env` for the active exchange (e.g. `MEXC_API_KEY`, `MEXC_API_SECRET`).
2. Set symbols in `configs/strategy.env` (e.g. `TRBUSDT`, `DOGEUSDT`).
3. Run:

```bash
python main.py -m papertrade -s trendline_breakout --symbols TRBUSDT DOGEUSDT
```

Paper mode **simulates** orders (many venues have no ccxt testnet) using live OHLCV and a virtual balance (`BACKTEST_INITIAL_CAPITAL`). The live engine polls closed bars on `TIMEFRAME`, applies HTF structure, scans `evaluate_prospect`, and manages SL/partial/trail like backtest.

### Live

Same command with `-m live` (real funds — use only after paper validation).

### Add another strategy

1. Implement under `strategy/implementations/your_strategy.py` (subclass `BaseStrategy`, set `name`).
2. Register via discovery (`strategy/discovery.py` picks up the module).
3. Add to `STRATEGIES` in `configs/strategy.env` or pass `-s your_strategy`.

### Add another exchange

1. Implement `BaseExchange` under `exchange/your_venue.py`.
2. Register in `exchange/exchange_factory.py`.
3. Add API key fields to `core/config.py` and `configs/exchange.env` if needed.
4. Ensure `market_data` historical downloader maps the venue in `EXCHANGE_NAME_MAP`.

## Project structure

```
├── configs/           Modular .env slices (strategy, risk, structure, exchange, …)
├── core/              Config loader and app settings
├── exchange/          Venue adapters (MEXC, Binance, Bybit) + paper wrapper
├── execution/         Live/paper portfolio engine, trade executor
├── market_data/       Candles, Parquet storage, dataset sync
├── market_structure/  HTF bias, BOS/CHoCH, MTF feeds
├── risk/              Sizing, exits, partial profit, trailing SL
├── strategy/          Base class, implementations, signal quality
├── backtest/          Portfolio backtest engine
└── main.py            CLI entry (backtest | papertrade | live | list)
```

## Configuration

See `configs/README.md` for load order: `configs/*.env` → root `.env` (secrets override).

## Version

```bash
python main.py --version
# Futures Trading Bot 0.2.0
```

Bump `VERSION` in `core/project.py` when you tag releases.

## Deployment

Systemd units, cloud-init, and rename from `mexc-bot` → `futures-trading-bot`:

```bash
./deploy/install-systemd.sh /home/ubuntu/futures-trading-bot ubuntu paper
```

Details: [`deploy/README.md`](deploy/README.md).

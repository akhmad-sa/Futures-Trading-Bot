# Modular environment — Futures Trading Bot

Settings are split by domain. Edit the file that matches the module you are tuning.

| File | Module |
|------|--------|
| `exchange.env` | API keys, exchange adapter, Telegram, DB |
| `logging.env` | Log level, structure diagnostics mode |
| `risk.env` | SL/TP, position sizing, drawdown, martingale |
| `market_structure.env` | MTF timeframes, BOS/CHoCH filters |
| `strategy.env` | Symbols, strategy name, signal score |
| `data.env` | Parquet candle storage, dataset sync |
| `backtest.env` | Portfolio replay, initial capital |
| `live.env` | Live / paper portfolio slots |

**Load order:** `configs/*.env` (alphabetical) → root `.env` (secrets + overrides).

Environment variables always win over files.

**Structure logging** (`logging.env`):

- `STRUCTURE_LOG_MODE=off` — disabled (default)
- `STRUCTURE_LOG_MODE=events` — file log on state change, CHoCH skip, near-miss (recommended)
- `STRUCTURE_LOG_MODE=full` — every bar to `logs/trading.log` only

Terminal output stays minimal via `utils/console.py` (HOLD, PICK, EXECUTION, EXIT).

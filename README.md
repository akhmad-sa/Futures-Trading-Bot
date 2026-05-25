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

## Project Structure

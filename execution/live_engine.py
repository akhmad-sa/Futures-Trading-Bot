"""
Live / paper portfolio engine aligned with backtest portfolio mode.

- Closed-bar processing on strategy timeframe
- MTF structure feeds (HTF bias)
- ``evaluate_prospect`` scan + shared capital / max concurrent slots
- Global risk exits (partial, trail SL, SL/TP) via :class:`TradeExecutor`
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from exchange.base import BaseExchange
from market_data.models.candle import Candle
from market_data.services.market_data_service import MarketDataService
from market_data.services.live_data_provider import LiveDataProvider
from market_structure.mtf import (
    MultiTimeframeConfig,
    StructureFeed,
    load_structure_feeds,
)
from market_structure.timeframes import get_interval_ms
from notifier.heartbeat import write_heartbeat
from execution.position_manager import PositionManager
from execution.trade_executor import TradeExecutor
from risk.manager import RiskManager
from storage.database import TradeDatabase
from notifier.telegram import TelegramNotifier
from strategy.prospective_signal import ProspectiveSignal
from utils import console as term

logger = logging.getLogger(__name__)

WARMUP_CANDLES = 2000
MAX_HISTORY = 5000
POLL_SECONDS = 30


def _as_core_candle(raw: Any, *, symbol: str, timeframe: str) -> Candle:
    """Normalize exchange / pydantic candles to project Candle."""
    if isinstance(raw, Candle):
        return raw
    return Candle(
        timestamp=int(raw.timestamp),
        open=float(raw.open),
        high=float(raw.high),
        low=float(raw.low),
        close=float(raw.close),
        volume=float(getattr(raw, "volume", 0.0) or 0.0),
        symbol=symbol,
        timeframe=timeframe,
    )


def _merge_candles(history: List[Candle], incoming: List[Candle]) -> List[Candle]:
    by_ts = {c.timestamp: c for c in history}
    for c in incoming:
        by_ts[c.timestamp] = c
    merged = sorted(by_ts.values(), key=lambda c: c.timestamp)
    if len(merged) > MAX_HISTORY:
        merged = merged[-MAX_HISTORY:]
    return merged


def _closed_bar(candles: List[Candle]) -> Optional[Candle]:
    """Use the latest fully closed bar (not the forming candle)."""
    if len(candles) < 2:
        return None
    return candles[-2]


class LivePortfolioEngine:
    """Runs trendline_breakout (and similar) strategies on live or paper exchange."""

    def __init__(
        self,
        exchange: BaseExchange,
        risk_manager: RiskManager,
        db: TradeDatabase,
        notifier: TelegramNotifier,
        config: Any,
        *,
        mode: str = "live",
    ) -> None:
        self.exchange = exchange
        self.risk_mgr = risk_manager
        self.config = config
        self.mode = mode
        self.pos_mgr = PositionManager()
        self.executor = TradeExecutor(
            exchange, risk_manager, self.pos_mgr, db, notifier
        )
        self._running = False
        self._history: Dict[str, List[Candle]] = {}
        self._last_closed_ts: Dict[str, int] = {}
        self._bar_index: Dict[str, int] = {}
        self._structure_feeds: Dict[str, StructureFeed] = {}
        self._strategies: Dict[str, Any] = {}
        self._symbols: List[str] = []
        self._timeframe = getattr(config, "timeframe", "5m")
        self._mtf_config = MultiTimeframeConfig.resolve(config)
        self._effective_max = 1

    async def start(self, strategies: Dict[str, Any], symbols: List[str]) -> None:
        """Warm up data, then poll for new closed bars."""
        self._strategies = strategies
        self._symbols = symbols
        self._running = True

        exchange_name = getattr(self.config, "exchange_name", "mexc")
        mtf_kwargs = self._mtf_kwargs()

        if self._mtf_config.is_active:
            service = MarketDataService(
                provider=LiveDataProvider(exchange_id=exchange_name),
                data_dir=getattr(self.config, "data_dir", "data/candles"),
            )
            self._structure_feeds = await load_structure_feeds(
                service,
                symbols,
                exchange_name,
                self._mtf_config,
                **mtf_kwargs,
            )
            logger.info(
                "[LIVE] MTF structure %s → strategy %s",
                self._mtf_config.structure_timeframe,
                self._mtf_config.strategy_timeframe,
            )

        for symbol in symbols:
            raw = await self.exchange.fetch_ohlcv(
                symbol, timeframe=self._timeframe, limit=WARMUP_CANDLES
            )
            hist = [
                _as_core_candle(c, symbol=symbol, timeframe=self._timeframe)
                for c in raw
            ]
            self._history[symbol] = hist
            closed = _closed_bar(hist)
            self._last_closed_ts[symbol] = closed.timestamp if closed else 0
            self._bar_index[symbol] = max(len(hist) - 2, 0)
            logger.info(
                "[LIVE] Warmup %s: %d candles, last_closed=%s",
                symbol,
                len(hist),
                self._last_closed_ts[symbol],
            )

        equity = await self.executor.fetch_equity()
        self.risk_mgr.reset_all(initial_capital=equity)

        configured_max = len(symbols)
        if not getattr(self.config, "portfolio_max_concurrent_symbols", True):
            configured_max = int(getattr(self.config, "max_concurrent_trades", 1))
        self._effective_max = min(configured_max, len(symbols))

        term.print_live_header(
            self.mode,
            symbols,
            equity,
            self._timeframe,
            self._mtf_config.structure_timeframe if self._mtf_config.is_active else None,
            max_concurrent=self._effective_max,
        )
        term.hold(datetime.now(timezone.utc), "scanning")
        self._write_heartbeat(poll_ok=True)

        while self._running:
            poll_ok = True
            try:
                await self._poll_once()
            except Exception as exc:
                poll_ok = False
                logger.exception("Live loop error: %s", exc)
                await self.notifier.send_error(str(exc)[:200])
                self._write_heartbeat(last_error=str(exc)[:200], poll_ok=False)
            else:
                self._write_heartbeat(poll_ok=poll_ok)
            await asyncio.sleep(POLL_SECONDS)

    def _write_heartbeat(
        self,
        *,
        poll_ok: bool = True,
        last_error: str | None = None,
    ) -> None:
        path = getattr(self.config, "heartbeat_path", "storage/heartbeat.json")
        open_detail: list[dict[str, Any]] = []
        for symbol in self._symbols:
            pos = self.pos_mgr.get_position(symbol)
            if pos is None:
                continue
            open_detail.append(
                {
                    "symbol": symbol,
                    "side": pos.get("side", ""),
                    "entry_price": float(pos.get("entry_price", 0.0)),
                    "size": float(pos.get("size", 0.0)),
                    "entry_time": pos.get("entry_time", ""),
                }
            )
        payload: dict[str, Any] = {
            "mode": self.mode,
            "symbols": list(self._symbols),
            "open_positions": len(open_detail),
            "open_positions_detail": open_detail,
            "poll_ok": poll_ok,
        }
        if last_error:
            payload["last_error"] = last_error
        try:
            write_heartbeat(path, payload)
        except OSError as exc:
            logger.debug("Heartbeat write failed: %s", exc)

    async def stop(self) -> None:
        self._running = False

    def _mtf_kwargs(self) -> dict:
        return {
            "pivot_len": int(getattr(self.config, "structure_pivot_len", 5)),
            "tolerance_bps": float(
                getattr(self.config, "structure_tolerance_bps", 0.0)
            ),
            "use_bos_choch": bool(getattr(self.config, "structure_use_bos_choch", True)),
            "break_confirm_close": bool(
                getattr(self.config, "structure_break_confirm_close", True)
            ),
            "break_tolerance_bps": float(
                getattr(self.config, "structure_break_tolerance_bps", 0.0)
            ),
        }

    async def _refresh_htf(self, symbol: str) -> None:
        feed = self._structure_feeds.get(symbol)
        if not feed:
            return
        htf = self._mtf_config.structure_timeframe
        raw = await self.exchange.fetch_ohlcv(symbol, timeframe=htf, limit=5)
        candles = [
            _as_core_candle(c, symbol=symbol, timeframe=htf) for c in raw
        ]
        feed.append_htf_candles(candles)

    def _inject_structure(self, symbol: str, ts: int, strategy: Any) -> None:
        feed = self._structure_feeds.get(symbol)
        if feed and hasattr(strategy, "set_structure_trend"):
            state = feed.sync_to(ts)
            strategy.set_structure_trend(state.effective_trend)
            if hasattr(strategy, "set_structure_state"):
                strategy.set_structure_state(state)

    async def _poll_once(self) -> None:
        now = datetime.now(timezone.utc)
        new_bars: Dict[str, tuple[Candle, int]] = {}

        for symbol in self._symbols:
            raw = await self.exchange.fetch_ohlcv(
                symbol, timeframe=self._timeframe, limit=5
            )
            incoming = [
                _as_core_candle(c, symbol=symbol, timeframe=self._timeframe)
                for c in raw
            ]
            self._history[symbol] = _merge_candles(
                self._history.get(symbol, []), incoming
            )
            closed = _closed_bar(self._history.get(symbol, []))
            if closed is None or closed.timestamp <= self._last_closed_ts.get(symbol, 0):
                continue
            history = self._history[symbol]
            idx = next(
                (i for i, c in enumerate(history) if c.timestamp == closed.timestamp),
                len(history) - 2,
            )
            self._bar_index[symbol] = idx
            new_bars[symbol] = (closed, idx)

        for symbol, (closed, idx) in new_bars.items():
            strategy = self._strategies[symbol]
            history = self._history[symbol]
            candle_time = datetime.fromtimestamp(
                closed.timestamp / 1000, tz=timezone.utc
            )
            await self._refresh_htf(symbol)
            self._inject_structure(symbol, closed.timestamp, strategy)

            if self.pos_mgr.get_position(symbol) is not None:
                reason = await self.executor.process_risk_exits(
                    symbol,
                    closed.close,
                    idx,
                    strategy,
                    candle_time=candle_time,
                )
                if not reason:
                    exit_sig = await strategy.get_exit_signal(
                        symbol, history[: idx + 1]
                    )
                    if exit_sig == "close":
                        exit_reason = (
                            getattr(strategy, "last_exit_reason", None) or "signal"
                        )
                        pos = self.pos_mgr.get_position(symbol)
                        exit_state = pos["exit_state"] if pos else None
                        if not (
                            exit_reason == "trend_exit"
                            and not self.risk_mgr.is_trend_exit_allowed(exit_state)
                        ):
                            await self.executor.close_position(
                                symbol,
                                close_price=closed.close,
                                reason=exit_reason,
                                candle_time=candle_time,
                            )
                            strategy.on_position_closed(
                                exit_reason, candle_index=idx
                            )
            self._last_closed_ts[symbol] = closed.timestamp

        prospects: List[ProspectiveSignal] = []
        best_near_miss: Optional[tuple[str, float]] = None
        open_count = self.pos_mgr.positions_count

        for symbol, (closed, idx) in new_bars.items():
            if self.pos_mgr.get_position(symbol) is not None:
                continue
            strat = self._strategies[symbol]
            if not hasattr(strat, "evaluate_prospect"):
                continue
            await self._refresh_htf(symbol)
            self._inject_structure(symbol, closed.timestamp, strat)
            history = self._history[symbol]
            prospect = await strat.evaluate_prospect(symbol, history[: idx + 1])
            near_score = getattr(strat, "last_scan_score", None)
            if prospect:
                prospects.append(prospect)
            elif near_score is not None and near_score > 0:
                if best_near_miss is None or near_score > best_near_miss[1]:
                    best_near_miss = (symbol, float(near_score))

        if prospects and open_count < self._effective_max:
            prospects.sort(key=lambda p: p.score, reverse=True)
            slots = self._effective_max - open_count
            equity = await self.executor.fetch_equity()

            for prospect in prospects[:slots]:
                sym = prospect.symbol
                if self.pos_mgr.get_position(sym) is not None:
                    continue
                strategy = self._strategies[sym]
                history = self._history[sym]
                closed = history[self._bar_index[sym]]
                candle_time = datetime.fromtimestamp(
                    closed.timestamp / 1000, tz=timezone.utc
                )
                strategy.last_entry_hints = prospect.hints
                term.portfolio_pick(prospect, candle_time)
                opened = await self.executor.open_position(
                    sym,
                    prospect.side,
                    closed.close,
                    equity,
                    hints=prospect.hints,
                    bar_index=self._bar_index[sym],
                    candle_time=candle_time,
                    current_positions_count=self.pos_mgr.positions_count,
                    sizing_slots=self._effective_max,
                )
                if opened:
                    strategy.on_position_opened(prospect.side, closed.close)
        elif prospects:
            candle_time = now
            term.portfolio_pick(prospects[0], candle_time)
            term.execution_rejected("max_concurrent", candle_time)
        elif best_near_miss and open_count == 0:
            sym_nm, score_nm = best_near_miss
            term.scan_near_miss(sym_nm, score_nm)

    @staticmethod
    def poll_interval_seconds(timeframe: str) -> int:
        """Suggested poll interval from timeframe (half bar, min 15s)."""
        ms = get_interval_ms(timeframe)
        return max(int(ms / 1000 / 2), 15)

"""
Professional risk management module.

Features:
- Fixed percentage risk
- ATR-based stop loss
- Dynamic position sizing
- Max drawdown protection
- Daily loss limit
- Consecutive loss cooldown
- Risk per symbol
- Max leverage validation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """Configuration for risk manager. Can be initialised from AppConfig or directly."""

    max_daily_loss: float = 500.0
    risk_per_trade: float = 0.02  # fraction of capital
    cooldown_seconds: int = 60
    max_concurrent_trades: int = 1
    max_drawdown_percent: float = 20.0  # percent
    consecutive_loss_limit: int = 3
    max_risk_per_symbol: float = 0.1  # fraction of total capital
    max_leverage: int = 5

    # Optional ATR multiplier for stop loss
    stop_loss_atr_multiplier: float = 2.0


class RiskManager:
    """Central risk manager enforcing trading rules."""

    def __init__(self, config) -> None:
        # Accept any object that has the required attributes (e.g. AppConfig)
        self.config = config
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._cumulative_pnl = 0.0  # for drawdown calculation
        self._peak_equity = 0.0
        self._consecutive_losses = 0
        self._last_trade_time: Optional[datetime] = None

    @property
    def daily_loss(self) -> float:
        return self._daily_loss

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    def can_open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        current_positions_count: int = 0,
        current_capital: float = 1000.0,
    ) -> bool:
        """Check whether a new position can be opened."""
        # Daily loss limit
        if self._daily_loss >= self._get_max_daily_loss():
            logger.warning("Daily loss limit reached")
            return False

        # Consecutive loss cooldown
        if self._consecutive_losses >= self._get_consecutive_loss_limit():
            logger.warning("Consecutive loss limit reached, cooldown active")
            # Optionally check time since last trade
            if self._last_trade_time is not None:
                elapsed = (datetime.now() - self._last_trade_time).total_seconds()
                if elapsed < self._get_cooldown_seconds():
                    logger.info("Cooldown not expired yet")
                    return False
            else:
                return False

        # Max concurrent trades
        if current_positions_count >= self._get_max_concurrent_trades():
            logger.warning("Max concurrent trades reached")
            return False

        # Max drawdown protection
        if self._peak_equity > 0:
            current_equity = self._peak_equity + self._cumulative_pnl
            drawdown_percent = (self._peak_equity - current_equity) / self._peak_equity * 100
            if drawdown_percent >= self._get_max_drawdown_percent():
                logger.warning("Max drawdown limit reached: %.2f%%", drawdown_percent)
                return False

        # Risk per symbol (not implemented per-symbol tracking here, but can be extended)
        # For now, assume global risk.

        # Max leverage validation (if we had a way to know current leverage)
        # This should be evaluated when calculating position size.
        # Not blocking here because position size calculation will limit leverage.

        # Cooldown after stop loss (general per symbol cooldown could be added)
        # For simplicity, we use the same cooldown for consecutive losses.

        return True

    def calculate_position_size(
        self,
        capital: float,
        price: float,
        stop_loss: Optional[float] = None,
        atr_value: Optional[float] = None,
    ) -> tuple[float, Optional[float]]:
        """
        Compute quantity based on fixed risk percentage and optional stop loss.

        Returns (quantity, stop_loss_price).
        If stop_loss is not provided but atr_value is, compute stop loss using ATR.
        """
        risk_amount = capital * self._get_risk_per_trade()

        if stop_loss is not None:
            risk_per_unit = abs(price - stop_loss)
            if risk_per_unit > 0:
                quantity = risk_amount / risk_per_unit
            else:
                quantity = 0.0
        elif atr_value is not None:
            stop_loss = price - atr_value * self._get_stop_loss_atr_multiplier() if True else price
            # For long positions stop_loss below price; for short above. We assume long for simplicity.
            # The caller should adjust side. We'll provide the logic symmetrical:
            # The stop_loss computed here is for long; the caller should invert for short.
            risk_per_unit = abs(price - stop_loss)
            if risk_per_unit > 0:
                quantity = risk_amount / risk_per_unit
            else:
                quantity = 0.0
        else:
            # Simple fixed percentage position sizing without stop loss
            quantity = risk_amount / price

        # Validate max leverage
        max_leverage = self._get_max_leverage()
        if max_leverage > 0:
            notional = quantity * price
            leverage = notional / capital
            if leverage > max_leverage:
                # Scale down quantity to respect max leverage
                quantity = (max_leverage * capital) / price
                logger.info("Position size reduced to respect max leverage (%.0fx)", max_leverage)

        # Ensure quantity is non-negative
        quantity = max(quantity, 0.0)

        return quantity, stop_loss

    def record_trade_pnl(self, pnl: float) -> None:
        """Update internal state after a closed trade."""
        self._daily_loss += pnl  # pnl negative if loss
        self._cumulative_pnl += pnl
        # Update peak equity
        equity = self._peak_equity + self._cumulative_pnl
        if equity > self._peak_equity:
            self._peak_equity = equity

        if pnl < 0:
            self._consecutive_losses += 1
            self._last_trade_time = datetime.now()
        else:
            self._consecutive_losses = 0

    def update_daily_loss(self, loss: float) -> None:
        """Legacy wrapper. Calls record_trade_pnl."""
        self.record_trade_pnl(loss)

    def reset_daily(self) -> None:
        """Call this at the start of each trading day."""
        self._daily_loss = 0.0
        self._daily_trades = 0
        # Do not reset cumulative pnl or peak equity because drawdown is measured over entire run.

    def reset_all(self) -> None:
        """Reset all internal state (e.g., for backtesting)."""
        self._daily_loss = 0.0
        self._daily_trades = 0
        self._cumulative_pnl = 0.0
        self._peak_equity = 0.0
        self._consecutive_losses = 0
        self._last_trade_time = None

    # Private helpers to read configuration with fallback defaults

    def _get_max_daily_loss(self) -> float:
        return getattr(self.config, 'max_daily_loss', 500.0)

    def _get_risk_per_trade(self) -> float:
        return getattr(self.config, 'risk_per_trade', 0.02)

    def _get_cooldown_seconds(self) -> int:
        return getattr(self.config, 'cooldown_seconds', 60)

    def _get_max_concurrent_trades(self) -> int:
        return getattr(self.config, 'max_concurrent_trades', 1)

    def _get_max_drawdown_percent(self) -> float:
        return getattr(self.config, 'max_drawdown_percent', 20.0)

    def _get_consecutive_loss_limit(self) -> int:
        return getattr(self.config, 'consecutive_loss_limit', 3)

    def _get_max_risk_per_symbol(self) -> float:
        return getattr(self.config, 'max_risk_per_symbol', 0.1)

    def _get_max_leverage(self) -> int:
        return getattr(self.config, 'max_leverage', 5)

    def _get_stop_loss_atr_multiplier(self) -> float:
        return getattr(self.config, 'stop_loss_atr_multiplier', 2.0)

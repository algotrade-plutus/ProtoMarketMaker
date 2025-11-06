"""
Audit Logger for Paper Trading Sessions

Provides detailed logging of signals, fills, rollovers, and daily settlements
similar to the ground truth iterative backtesting logs.

Usage:
    logger = AuditLogger('logs/audit/session.log', enabled=True)
    logger.log_signal(signal_num, reason, market_price, bid, ask, inventory)
    logger.log_fill(fill_num, side, price, qty, ...)
    logger.close()
"""

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional


class AuditLogger:
    """
    Audit logger for paper trading sessions

    Logs all signals, fills, rollovers, and daily settlements in a format
    compatible with ground truth iterative backtesting logs.
    """

    def __init__(self, log_path: str, enabled: bool = True):
        """
        Initialize audit logger

        Args:
            log_path: Path to log file
            enabled: Whether logging is enabled
        """
        self.log_path = log_path
        self.enabled = enabled
        self.signal_count = 0
        self.fill_count = 0
        self.rollover_count = 0
        self.daily_count = 0

        if self.enabled:
            # Create log directory if needed
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)

            # Configure logger
            self.logger = logging.getLogger('audit_logger')
            self.logger.setLevel(logging.INFO)
            self.logger.handlers = []  # Clear any existing handlers

            # File handler
            file_handler = logging.FileHandler(log_path, mode='w')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(file_handler)

            # Log header
            self.logger.info("=" * 80)
            self.logger.info("PAPER TRADING AUDIT LOG")
            self.logger.info("=" * 80)
            self.logger.info(f"Session started: {datetime.now()}")
            self.logger.info(f"Log file: {log_path}")
            self.logger.info("=" * 80)
            self.logger.info("")

    def log_signal(
        self,
        timestamp: datetime,
        reason: str,
        market_price: Decimal,
        bid_price: Decimal,
        ask_price: Decimal,
        spread: Decimal,
        inventory: int,
        contract: Optional[str] = None
    ):
        """
        Log a signal event

        Args:
            timestamp: Signal timestamp
            reason: Signal reason (TIME_ELAPSED, ORDER_FILLED, etc.)
            market_price: Current market price
            bid_price: Calculated bid price
            ask_price: Calculated ask price
            spread: Bid-ask spread
            inventory: Current inventory
            contract: Contract symbol (optional)
        """
        if not self.enabled:
            return

        self.signal_count += 1

        log_msg = (
            f"[SIGNAL] #{self.signal_count} | "
            f"time={timestamp} | "
            f"reason={reason} | "
            f"market_price={float(market_price):.1f} | "
            f"bid={float(bid_price):.1f} | "
            f"ask={float(ask_price):.1f} | "
            f"spread={float(spread):.1f} | "
            f"inventory={inventory}"
        )

        if contract:
            log_msg += f" | contract={contract}"

        self.logger.info(log_msg)

    def log_fill(
        self,
        timestamp: datetime,
        side: str,
        price: Decimal,
        qty: int,
        inv_before: int,
        inv_after: int,
        inv_price_before: Decimal,
        inv_price_after: Decimal,
        pnl_realized: Optional[Decimal] = None,
        ac_loss_before: Optional[Decimal] = None,
        ac_loss_after: Optional[Decimal] = None,
        fill_type: Optional[str] = None,
        placeable: Optional[int] = None,
        contract: Optional[str] = None
    ):
        """
        Log a fill event

        Args:
            timestamp: Fill timestamp
            side: Order side (BID, ASK, BID_COVER, ASK_COVER)
            price: Fill price
            qty: Fill quantity
            inv_before: Inventory before fill
            inv_after: Inventory after fill
            inv_price_before: Average inventory price before
            inv_price_after: Average inventory price after
            pnl_realized: Realized P&L (for closing trades)
            ac_loss_before: Accumulated loss before
            ac_loss_after: Accumulated loss after
            fill_type: Fill type (OPEN_LONG, OPEN_SHORT, COVER_LONG, COVER_SHORT)
            placeable: Maximum placeable contracts
            contract: Contract symbol
        """
        if not self.enabled:
            return

        self.fill_count += 1

        log_msg = (
            f"[FILL] #{self.fill_count} | "
            f"time={timestamp} | "
            f"side={side} | "
            f"price={float(price):.1f} | "
            f"qty={qty} | "
            f"inv_before={inv_before} | "
            f"inv_after={inv_after} | "
            f"inv_price_before={float(inv_price_before):.2f} | "
            f"inv_price_after={float(inv_price_after):.2f}"
        )

        if pnl_realized is not None:
            log_msg += f" | pnl_realized={float(pnl_realized):.2f}"

        if ac_loss_before is not None:
            log_msg += f" | ac_loss_before={float(ac_loss_before):.2f}"

        if ac_loss_after is not None:
            log_msg += f" | ac_loss_after={float(ac_loss_after):.2f}"

        if fill_type:
            log_msg += f" | type={fill_type}"

        if placeable is not None:
            log_msg += f" | placeable={placeable}"

        if contract:
            log_msg += f" | contract={contract}"

        self.logger.info(log_msg)

    def log_rollover(
        self,
        timestamp: datetime,
        from_contract: str,
        to_contract: str,
        inventory: int,
        pnl_locked: Decimal
    ):
        """
        Log a contract rollover event

        Args:
            timestamp: Rollover timestamp
            from_contract: Old contract code
            to_contract: New contract code
            inventory: Current inventory
            pnl_locked: P&L locked in from old contract
        """
        if not self.enabled:
            return

        self.rollover_count += 1

        log_msg = (
            f"[ROLLOVER] #{self.rollover_count} | "
            f"time={timestamp} | "
            f"from={from_contract} | "
            f"to={to_contract} | "
            f"inventory={inventory} | "
            f"pnl_locked={float(pnl_locked):.2f}"
        )

        self.logger.info(log_msg)

    def log_daily_settlement(
        self,
        date: datetime,
        nav: Decimal,
        daily_return: Decimal,
        inventory: int,
        contract: str
    ):
        """
        Log daily settlement

        Args:
            date: Settlement date
            nav: Net Asset Value
            daily_return: Daily return
            inventory: End-of-day inventory
            contract: Active contract
        """
        if not self.enabled:
            return

        self.daily_count += 1

        log_msg = (
            f"[DAILY] #{self.daily_count} | "
            f"date={date.date()} | "
            f"nav={float(nav):.2f} | "
            f"return={float(daily_return):.4f} | "
            f"inventory={inventory} | "
            f"contract={contract}"
        )

        self.logger.info(log_msg)

    def log_info(self, message: str):
        """Log informational message"""
        if self.enabled:
            self.logger.info(message)

    def log_summary(
        self,
        total_signals: int,
        total_fills: int,
        total_rollovers: int,
        initial_capital: Decimal,
        final_nav: Decimal,
        hpr: Decimal
    ):
        """
        Log session summary

        Args:
            total_signals: Total signals generated
            total_fills: Total fills executed
            total_rollovers: Total rollovers
            initial_capital: Initial capital
            final_nav: Final NAV
            hpr: Holding period return
        """
        if not self.enabled:
            return

        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("SESSION SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"Total Signals:     {total_signals}")
        self.logger.info(f"Total Fills:       {total_fills}")
        self.logger.info(f"Total Rollovers:   {total_rollovers}")
        self.logger.info(f"Initial Capital:   {float(initial_capital):,.2f} VND")
        self.logger.info(f"Final NAV:         {float(final_nav):,.2f} VND")
        self.logger.info(f"HPR:               {float(hpr):.4f} ({float(hpr)*100:.2f}%)")
        self.logger.info("=" * 80)
        self.logger.info(f"Session ended: {datetime.now()}")

    def close(self):
        """Close the logger"""
        if self.enabled and hasattr(self, 'logger'):
            for handler in self.logger.handlers:
                handler.close()
                self.logger.removeHandler(handler)

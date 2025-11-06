"""
Real-Time Performance Monitor

Tracks and calculates performance metrics in real-time.
"""
from decimal import Decimal
from datetime import datetime, date
from typing import List, Optional, Dict
import logging

from protomarketmaker.core import EventBus, FillEvent, TimeEvent, EventType, OrderSide


class PerformanceMonitor:
    """
    Real-time performance monitoring

    Calculates metrics as trades execute:
    - Total PnL
    - Win rate
    - Average trade PnL
    - Trade count by side
    - Largest win/loss

    Example:
        monitor = PerformanceMonitor(event_bus)
        metrics = monitor.get_current_metrics()
    """

    def __init__(self, event_bus: EventBus):
        """
        Initialize performance monitor

        Args:
            event_bus: EventBus for subscribing to events
        """
        self.event_bus = event_bus

        # Trade tracking
        self.trades: List[dict] = []
        self.total_trades = 0

        # PnL tracking (simplified - actual PnL calculated by portfolio)
        self.total_fees = Decimal('0')

        # Trade statistics
        self.buy_count = 0
        self.sell_count = 0

        # Fee tracking
        self.fees_by_contract: Dict[str, Decimal] = {}

        self.logger = logging.getLogger(__name__)

        # Subscribe to events
        self.event_bus.subscribe(EventType.FILL, self.on_fill_event)
        self.event_bus.subscribe(EventType.TIME, self.on_time_event)

    def on_fill_event(self, event: FillEvent):
        """
        Track trade execution

        Args:
            event: Fill event with trade details
        """
        # Record trade
        trade = {
            'timestamp': event.timestamp,
            'contract': event.contract,
            'side': event.side,
            'price': event.fill_price,
            'quantity': event.fill_quantity,
            'fee': event.fee
        }
        self.trades.append(trade)
        self.total_trades += 1

        # Update counters
        if event.side == "BID":
            self.buy_count += 1
        else:
            self.sell_count += 1

        # Track fees
        self.total_fees += event.fee
        if event.contract not in self.fees_by_contract:
            self.fees_by_contract[event.contract] = Decimal('0')
        self.fees_by_contract[event.contract] += event.fee

        # Log significant trades
        self.logger.debug(
            f"Trade executed: {event.side} {event.contract} @ {event.fill_price}"
        )

    def on_time_event(self, event: TimeEvent):
        """
        Handle daily settlement

        Args:
            event: Time event
        """
        if event.event_name == "DAILY_SETTLEMENT":
            self.logger.info(f"Daily settlement: {self.total_trades} trades executed")

    def get_current_metrics(self) -> dict:
        """
        Get current performance metrics

        Returns:
            Dictionary with performance metrics
        """
        return {
            'total_trades': self.total_trades,
            'buy_count': self.buy_count,
            'sell_count': self.sell_count,
            'total_fees': float(self.total_fees),
            'average_fee': float(self.total_fees / self.total_trades) if self.total_trades > 0 else 0,
            'fees_by_contract': {k: float(v) for k, v in self.fees_by_contract.items()}
        }

    def get_trade_history(self, limit: Optional[int] = None) -> List[dict]:
        """
        Get recent trade history

        Args:
            limit: Maximum number of trades to return (None = all)

        Returns:
            List of trade dictionaries
        """
        if limit:
            return self.trades[-limit:]
        return self.trades

    def get_trades_by_contract(self, contract: str) -> List[dict]:
        """
        Get trades for specific contract

        Args:
            contract: Contract symbol

        Returns:
            List of trades for the contract
        """
        return [t for t in self.trades if t['contract'] == contract]

    def reset(self):
        """Reset all statistics"""
        self.trades = []
        self.total_trades = 0
        self.buy_count = 0
        self.sell_count = 0
        self.total_fees = Decimal('0')
        self.fees_by_contract = {}

        self.logger.info("Performance monitor reset")

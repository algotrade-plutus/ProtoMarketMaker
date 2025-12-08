"""
Market-Making Strategy Engine

Refactored from backtesting.py to use event-driven architecture.
Generates bid/ask signals based on:
- Current market price
- Inventory position
- Step parameter (optimized: 2.9)
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from typing import Optional
import logging

from protomarketmaker.core import EventBus, MarketDataEvent, SignalEvent, FillEvent, EventType
from .portfolio import PortfolioManager


class MarketMakerStrategy:
    """
    Inventory-based market making strategy

    Generates trading signals (bid/ask prices) based on:
    - Current inventory (from portfolio)
    - Market price (from market data events)
    - Step parameter

    Triggers:
    - Time-based: Every 15 seconds
    - Event-based: Upon order fill

    Example:
        strategy = MarketMakerStrategy(
            event_bus=bus,
            portfolio=portfolio,
            step=Decimal("2.9"),
            update_interval_seconds=15
        )
    """

    def __init__(
        self,
        event_bus: EventBus,
        portfolio: PortfolioManager,
        step: Decimal,
        update_interval_seconds: int = 15
    ):
        """
        Initialize strategy engine

        Args:
            event_bus: Event bus for publishing/subscribing
            portfolio: Portfolio manager for position tracking
            step: Step parameter for bid/ask calculation
            update_interval_seconds: Time between order updates (default 15)
        """
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.step = step
        self.update_interval = timedelta(seconds=update_interval_seconds)

        # State tracking
        self.last_update_time: Optional[datetime] = None
        self.last_signal_timestamp: Optional[datetime] = None  # Track last signal timestamp
        self.current_contract: str = "VN30F1M"
        self.current_price: Optional[Decimal] = None

        self.logger = logging.getLogger(__name__)

        # Subscribe to events
        self.event_bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        self.event_bus.subscribe(EventType.FILL, self.on_fill_event)
        self.event_bus.subscribe(EventType.ROLLOVER, self.on_rollover_event)

    def calculate_bid_ask(
        self,
        price: Decimal,
        inventory: int
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate bid/ask prices based on current inventory

        Formula from backtesting.py:
        bid = (price - step) - step * max(inventory, 0) * 0.02
        ask = (price + step) - step * min(inventory, 0) * 0.02

        Args:
            price: Current market price
            inventory: Current inventory (positive=long, negative=short)

        Returns:
            Tuple of (bid_price, ask_price)
        """
        # Calculate bid (decreases with positive inventory)
        bid = (
            price - self.step * Decimal(max(inventory, 0) * 0.02 + 1)
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        # Calculate ask (increases with negative inventory)
        ask = (
            price - self.step * Decimal(min(inventory, 0) * 0.02 - 1)
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        return bid, ask

    def should_update_orders(
        self,
        current_time: datetime
    ) -> tuple[bool, str]:
        """
        Determine if orders should be updated

        Args:
            current_time: Current timestamp

        Returns:
            Tuple of (should_update, reason)
            reason: "TIME_ELAPSED" or ""
        """
        # First update or time-based update (every 15 seconds)
        # Note: Using "TIME_ELAPSED" for first signal to match original backtest labeling
        if self.last_update_time is None or current_time >= self.last_update_time + self.update_interval:
            return True, "TIME_ELAPSED"

        return False, ""

    def on_market_data(self, event: MarketDataEvent):
        """
        Handle market data event

        Updates current price and checks if orders should be updated
        based on time elapsed.

        Args:
            event: Market data event with price update
        """
        self.current_price = event.price
        self.current_contract = event.contract

        # Check if we should update orders
        should_update, reason = self.should_update_orders(event.timestamp)

        if should_update:
            self.generate_signal(event.timestamp, reason)

    def on_fill_event(self, event: FillEvent):
        """
        Handle order fill - update orders immediately

        When an order fills, inventory changes, so we need to
        recalculate bid/ask prices immediately.

        Args:
            event: Fill event with execution details
        """
        # IMPORTANT: If we already generated a TIME_ELAPSED signal at this exact
        # timestamp (which happens at day boundaries), don't generate ORDER_FILLED.
        # This matches original backtest behavior where only one signal is generated
        # per timestamp. The TIME_ELAPSED signal will be updated with post-fill
        # inventory on the next tick.
        if self.current_price and self.last_signal_timestamp != event.timestamp:
            self.generate_signal(event.timestamp, "ORDER_FILLED")

    def on_rollover_event(self, event):
        """
        Handle contract rollover event

        Updates the current contract being traded when futures contract expires.

        Args:
            event: RolloverEvent with old/new contract information
        """
        from protomarketmaker.core.event import RolloverEvent
        if isinstance(event, RolloverEvent):
            self.logger.info(
                f"Strategy: Contract rollover from {event.old_contract} "
                f"to {event.new_contract}"
            )
            self.current_contract = event.new_contract
            # Update current price to new contract's price
            self.current_price = event.new_price

    def generate_signal(self, timestamp: datetime, reason: str):
        """
        Generate trading signal (bid/ask prices)

        Calculates new bid/ask prices based on current inventory
        and publishes SignalEvent to EventBus.

        Args:
            timestamp: Signal generation time
            reason: Reason for update ("INITIAL", "TIME_ELAPSED", "ORDER_FILLED")
        """
        # IMPORTANT: Skip TIME_ELAPSED signals if we already generated a signal
        # at this exact timestamp. This prevents duplicate signals when a fill
        # happens at the same timestamp as a time-based update (e.g., first tick
        # of a new trading day after weekend/holiday).
        if reason == "TIME_ELAPSED" and self.last_signal_timestamp == timestamp:
            self.logger.debug(
                f"Skipping duplicate TIME_ELAPSED signal at {timestamp} "
                f"(already generated signal at this timestamp)"
            )
            return

        # Get current inventory
        position = self.portfolio.get_position(self.current_contract)
        inventory = position.quantity

        # Calculate bid/ask prices
        bid_price, ask_price = self.calculate_bid_ask(
            self.current_price,
            inventory
        )

        # Create and publish signal event
        signal = SignalEvent(
            timestamp=timestamp,
            contract=self.current_contract,
            signal_type="UPDATE_BID_ASK",
            bid_price=bid_price,
            ask_price=ask_price,
            reason=reason
        )

        self.event_bus.publish(signal)

        # Track this signal's timestamp
        self.last_signal_timestamp = timestamp

        # IMPORTANT: Only update last_update_time for time-based signals
        # This matches original backtest behavior where old_timestamp
        # is only updated when TIME_ELAPSED, not on ORDER_FILLED
        if reason == "TIME_ELAPSED":
            self.last_update_time = timestamp

        self.logger.info(
            f"Signal: {self.current_contract} "
            f"BID={bid_price} ASK={ask_price} "
            f"(inventory={inventory}, reason={reason})"
        )

    def reset(self):
        """Reset strategy state (useful for testing)"""
        self.last_update_time = None
        self.last_signal_timestamp = None
        self.current_price = None

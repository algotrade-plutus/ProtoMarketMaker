"""
Mock Execution Engine

Simulates order execution for paper trading.
Matches orders when market price crosses bid/ask levels.
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict
import logging

from core.event import EventBus, OrderEvent, FillEvent, MarketDataEvent
from core.enums import EventType


class MockExecutionEngine:
    """
    Simulates order execution for paper trading

    Responsibilities:
    - Monitor pending orders
    - Check fill conditions on market data updates
    - Generate fill events when orders match
    - Apply realistic fees

    Example:
        execution = MockExecutionEngine(event_bus)
    """

    # Fee per contract (from backtesting.py: 0.4% * 100 multiplier)
    FEE_PER_CONTRACT = Decimal('0.4') * Decimal('100')

    def __init__(self, event_bus: EventBus, risk_manager=None):
        """
        Initialize mock execution engine

        Args:
            event_bus: Event bus for publishing/subscribing
            risk_manager: Risk manager for pre-fill margin checks (optional)
        """
        self.event_bus = event_bus
        self.risk_manager = risk_manager
        self.pending_orders: Dict[str, OrderEvent] = {}
        self.current_prices: Dict[str, Decimal] = {}
        self.logger = logging.getLogger(__name__)
        self.rejected_fills = 0

        # Subscribe to events
        self.event_bus.subscribe(EventType.ORDER, self.on_order_event)
        self.event_bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    def on_order_event(self, event: OrderEvent):
        """
        Register or remove orders for execution monitoring

        Args:
            event: Order event (SUBMITTED or CANCELLED)
        """
        if event.status == "SUBMITTED":
            self.pending_orders[event.order_id] = event
            self.logger.debug(
                f"Registered order {event.order_id[:8]}... "
                f"{event.side} {event.contract} @ {event.price}"
            )

        elif event.status == "CANCELLED":
            if event.order_id in self.pending_orders:
                del self.pending_orders[event.order_id]
                self.logger.debug(f"Removed order {event.order_id[:8]}...")

    def on_market_data(self, event: MarketDataEvent):
        """
        Check if any pending orders should be filled

        Args:
            event: Market data event with price update
        """
        self.current_prices[event.contract] = event.price

        # Check each pending order for fill condition
        orders_to_fill = []

        for order_id, order_event in list(self.pending_orders.items()):
            if order_event.contract != event.contract:
                continue

            should_fill, fill_price = self._check_fill_condition(
                order_event,
                event.price
            )

            if should_fill:
                orders_to_fill.append((order_id, order_event, fill_price))

        # Execute fills (with pre-fill margin check)
        for order_id, order_event, fill_price in orders_to_fill:
            # Re-check margin before fill (market conditions may have changed)
            # IMPORTANT: Check margin for BOTH BID and ASK when opening positions
            if self.risk_manager:
                # Create temp order for validation
                from core.order import Order
                from core.enums import OrderSide, OrderStatus
                temp_order = Order(
                    contract=order_event.contract,
                    side=OrderSide.BID if order_event.side == "BID" else OrderSide.ASK,
                    price=fill_price,
                    quantity=order_event.quantity,
                    status=OrderStatus.SUBMITTED
                )

                is_valid = self.risk_manager.validate_order(temp_order)
                if not is_valid:
                    self.rejected_fills += 1
                    self.logger.warning(
                        f"Fill rejected: {order_id[:8]}... {order_event.side} "
                        f"{order_event.contract} @ {fill_price} (insufficient margin at fill time)"
                    )
                    del self.pending_orders[order_id]  # Remove order without filling
                    continue

            # Execute the fill
            self._execute_fill(order_event, fill_price, event.timestamp)
            del self.pending_orders[order_id]

            # Process fill immediately so next margin check sees updated portfolio
            self.event_bus.process_events()

    def _check_fill_condition(
        self,
        order_event: OrderEvent,
        market_price: Decimal
    ) -> tuple[bool, Decimal]:
        """
        Determine if order should be filled

        Matching logic from backtesting.py:
        - BID fills if market price <= bid price
        - ASK fills if market price >= ask price

        Args:
            order_event: Order to check
            market_price: Current market price

        Returns:
            Tuple of (should_fill, fill_price)
        """
        if order_event.side == "BID":
            # Buy order fills when price drops to/below bid
            if market_price <= order_event.price:
                return True, market_price

        elif order_event.side == "ASK":
            # Sell order fills when price rises to/above ask
            if market_price >= order_event.price:
                return True, market_price

        return False, Decimal('0')

    def _execute_fill(
        self,
        order_event: OrderEvent,
        fill_price: Decimal,
        timestamp: datetime
    ):
        """
        Generate fill event

        Args:
            order_event: Order being filled
            fill_price: Execution price
            timestamp: Fill timestamp
        """
        fill = FillEvent(
            timestamp=timestamp,
            order_id=order_event.order_id,
            contract=order_event.contract,
            side=order_event.side,
            fill_price=fill_price,
            fill_quantity=order_event.quantity,
            fee=self.FEE_PER_CONTRACT * order_event.quantity
        )

        self.event_bus.publish(fill)

        self.logger.info(
            f"Fill: {order_event.order_id[:8]}... "
            f"{order_event.side} {order_event.contract} "
            f"@ {fill_price} (fee={fill.fee})"
        )

    def get_pending_count(self) -> int:
        """Get number of pending orders"""
        return len(self.pending_orders)

    def get_pending_orders_by_contract(self, contract: str) -> list:
        """Get pending orders for specific contract"""
        return [
            o for o in self.pending_orders.values()
            if o.contract == contract
        ]

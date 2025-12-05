"""
Order Management System (OMS)

Responsibilities:
- Create and validate orders
- Track order lifecycle
- Cancel/modify orders
- Maintain order book
"""
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal
import logging

from protomarketmaker.core import (
    Order,
    OrderStatus,
    OrderSide,
    EventType,
    EventBus,
    OrderEvent,
    SignalEvent,
    FillEvent,
)


class OrderManager:
    """
    Order Management System

    Manages the complete lifecycle of orders from creation to completion.
    Integrates with EventBus for event-driven updates.

    Example:
        oms = OrderManager(event_bus, risk_manager)
        order = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        oms.submit_order(order)
    """

    def __init__(self, event_bus: EventBus, risk_manager=None):
        """
        Initialize OMS

        Args:
            event_bus: Event bus for publishing events
            risk_manager: Risk manager for pre-trade checks (optional)
        """
        self.event_bus = event_bus
        self.risk_manager = risk_manager
        self.orders: Dict[str, Order] = {}  # All orders
        self.active_orders: Dict[str, Order] = {}  # Active orders only
        self.logger = logging.getLogger(__name__)

        # Subscribe to events
        self.event_bus.subscribe(EventType.SIGNAL, self.on_signal_event)
        self.event_bus.subscribe(EventType.FILL, self.on_fill_event)

    def create_order(
        self,
        contract: str,
        side: OrderSide,
        price: Decimal,
        quantity: int = 1
    ) -> Order:
        """
        Create new order

        Args:
            contract: Contract symbol (VN30F1M, VN30F2M)
            side: Order side (BID/ASK)
            price: Limit price
            quantity: Number of contracts

        Returns:
            Created order object
        """
        order = Order(
            contract=contract,
            side=side,
            price=price,
            quantity=quantity,
            status=OrderStatus.CREATED
        )
        self.orders[order.order_id] = order

        self.logger.debug(
            f"Order created: {order.order_id[:8]} {side.value} "
            f"{contract} @ {price} x{quantity}"
        )

        return order

    def submit_order(self, order: Order) -> bool:
        """
        Submit order after risk validation

        Args:
            order: Order to submit

        Returns:
            True if submitted successfully, False if rejected
        """
        # Risk check (if risk manager available)
        if self.risk_manager:
            if not self.risk_manager.validate_order(order):
                order.status = OrderStatus.REJECTED
                self.logger.warning(
                    f"Order {order.order_id[:8]} rejected by risk manager"
                )
                return False

        # Update status
        order.status = OrderStatus.SUBMITTED
        order.submitted_at = datetime.now()
        self.active_orders[order.order_id] = order

        # Publish order event
        event = OrderEvent(
            timestamp=datetime.now(),
            order_id=order.order_id,
            contract=order.contract,
            side=order.side.value,
            price=order.price,
            quantity=order.quantity,
            status=order.status.value
        )
        self.event_bus.publish(event)

        self.logger.info(
            f"Order submitted: {order.order_id[:8]} {order.side.value} "
            f"{order.contract} @ {order.price} x{order.quantity}"
        )

        return True

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel active order

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled, False if not found or already terminal
        """
        if order_id not in self.active_orders:
            self.logger.warning(
                f"Cannot cancel order {order_id[:8]}: not active"
            )
            return False

        order = self.active_orders[order_id]

        if not order.can_cancel():
            self.logger.warning(
                f"Cannot cancel order {order_id[:8]}: status={order.status.value}"
            )
            return False

        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now()
        del self.active_orders[order_id]

        # Publish cancellation event
        event = OrderEvent(
            timestamp=datetime.now(),
            order_id=order.order_id,
            contract=order.contract,
            side=order.side.value,
            price=order.price,
            quantity=order.quantity,
            status=OrderStatus.CANCELLED.value
        )
        self.event_bus.publish(event)

        self.logger.info(f"Order cancelled: {order_id[:8]}")
        return True

    def cancel_all_orders(self, contract: Optional[str] = None):
        """
        Cancel all active orders (optionally for specific contract)

        Args:
            contract: Contract symbol to filter (None = all contracts)
        """
        orders_to_cancel = list(self.active_orders.values())

        if contract:
            orders_to_cancel = [
                o for o in orders_to_cancel if o.contract == contract
            ]

        for order in orders_to_cancel:
            self.cancel_order(order.order_id)

        self.logger.info(
            f"Cancelled {len(orders_to_cancel)} orders"
            + (f" for {contract}" if contract else "")
        )

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)

    def get_active_orders(self) -> List[Order]:
        """Get all active orders"""
        return list(self.active_orders.values())

    def get_active_orders_by_contract(self, contract: str) -> List[Order]:
        """Get active orders for specific contract"""
        return [
            o for o in self.active_orders.values()
            if o.contract == contract
        ]

    def on_signal_event(self, event: SignalEvent):
        """
        Handle strategy signal to create new orders

        Args:
            event: Signal event with bid/ask prices
        """
        # Cancel old orders for this contract
        self.cancel_all_orders(contract=event.contract)

        # Create new bid order
        bid_order = self.create_order(
            contract=event.contract,
            side=OrderSide.BID,
            price=event.bid_price,
            quantity=1
        )
        self.submit_order(bid_order)

        # Create new ask order
        ask_order = self.create_order(
            contract=event.contract,
            side=OrderSide.ASK,
            price=event.ask_price,
            quantity=1
        )
        self.submit_order(ask_order)

        self.logger.debug(
            f"Orders updated from signal: BID={event.bid_price} "
            f"ASK={event.ask_price} (reason={event.reason})"
        )

    def on_fill_event(self, event: FillEvent):
        """
        Handle order fill notification

        Args:
            event: Fill event with execution details
        """
        if event.order_id not in self.orders:
            self.logger.error(
                f"Fill event for unknown order {event.order_id[:8]}"
            )
            return

        order = self.orders[event.order_id]
        order.filled_quantity += event.fill_quantity
        order.filled_price = event.fill_price
        order.filled_at = event.timestamp

        # Update status
        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
            if order.order_id in self.active_orders:
                del self.active_orders[order.order_id]
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        self.logger.info(
            f"Order filled: {order.order_id[:8]} "
            f"{event.fill_quantity} @ {event.fill_price} "
            f"(fee={event.fee}) [{order.status.value}]"
        )

    def on_order_event(self, event):
        """
        Handle order status updates from execution engine

        Args:
            event: OrderEvent with status updates (ACCEPTED, REJECTED, CANCELLED)
        """
        if not hasattr(event, 'order_id') or not hasattr(event, 'status'):
            return

        if event.order_id not in self.orders:
            self.logger.warning(f"Order event for unknown order: {event.order_id[:8]}")
            return

        order = self.orders[event.order_id]
        old_status = order.status

        # Update order status based on event
        if event.status == "ACCEPTED":
            # Order acknowledged by exchange
            order.status = OrderStatus.ACCEPTED
            self.logger.info(f"Order accepted by exchange: {event.order_id[:8]}")

        elif event.status == "REJECTED":
            # Order rejected by exchange
            order.status = OrderStatus.REJECTED
            order.rejection_reason = getattr(event, 'rejection_reason', 'Unknown')

            # Remove from active orders
            if event.order_id in self.active_orders:
                del self.active_orders[event.order_id]

            self.logger.warning(
                f"Order rejected: {event.order_id[:8]} - {order.rejection_reason}"
            )

        elif event.status == "CANCELLED":
            # Order cancelled
            order.status = OrderStatus.CANCELLED

            # Remove from active orders
            if event.order_id in self.active_orders:
                del self.active_orders[event.order_id]

            self.logger.info(f"Order cancelled: {event.order_id[:8]}")

    def get_statistics(self) -> dict:
        """Get OMS statistics"""
        total_orders = len(self.orders)
        active_count = len(self.active_orders)
        filled_count = sum(
            1 for o in self.orders.values()
            if o.status == OrderStatus.FILLED
        )
        cancelled_count = sum(
            1 for o in self.orders.values()
            if o.status == OrderStatus.CANCELLED
        )
        rejected_count = sum(
            1 for o in self.orders.values()
            if o.status == OrderStatus.REJECTED
        )

        return {
            'total_orders': total_orders,
            'active_orders': active_count,
            'filled_orders': filled_count,
            'cancelled_orders': cancelled_count,
            'rejected_orders': rejected_count
        }

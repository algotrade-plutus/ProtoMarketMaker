"""
PaperBroker Execution Engine

Real execution engine using PaperBroker FIX protocol for order submission.
Replaces MockExecutionEngine with actual order execution via FIX 4.4.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from threading import Timer

from core.event import EventBus, OrderEvent
from core.enums import EventType
from connectors.paperbroker_connector import PaperBrokerConnector


class PaperBrokerExecutionEngine:
    """
    Real execution engine using PaperBroker FIX protocol

    Replaces MockExecutionEngine with actual FIX order submission.
    Maintains same interface for plugin compatibility.

    Key differences from MockExecutionEngine:
    - Orders submitted to real exchange via FIX
    - Asynchronous order acknowledgment
    - Support for partial fills
    - Connection management
    - Order timeout handling

    Example:
        connector = PaperBrokerConnector(event_bus, **config)
        execution = PaperBrokerExecutionEngine(
            event_bus=event_bus,
            connector=connector,
            risk_manager=risk_manager
        )
    """

    def __init__(
        self,
        event_bus: EventBus,
        connector: PaperBrokerConnector,
        risk_manager=None,
        order_timeout_seconds: int = 60,
        max_pending_orders: int = 10
    ):
        """
        Initialize PaperBroker execution engine

        Args:
            event_bus: ProtoMarketMaker event bus
            connector: PaperBroker FIX connector
            risk_manager: Optional risk manager for pre-trade checks
            order_timeout_seconds: Timeout for order acknowledgment
            max_pending_orders: Maximum number of pending orders
        """
        self.event_bus = event_bus
        self.connector = connector
        self.risk_manager = risk_manager
        self.order_timeout_seconds = order_timeout_seconds
        self.max_pending_orders = max_pending_orders
        self.logger = logging.getLogger(__name__)

        # Track pending orders (awaiting acknowledgment)
        self.pending_orders: Dict[str, OrderEvent] = {}

        # Track timeout timers
        self.timeout_timers: Dict[str, Timer] = {}

        # Subscribe to order events from OMS
        self.event_bus.subscribe(EventType.ORDER, self.on_order_event)

        # Subscribe to order acknowledgments (from connector)
        self.event_bus.subscribe(EventType.ORDER, self.on_order_acknowledged)

        self.logger.info(
            f"PaperBrokerExecutionEngine initialized "
            f"(timeout={order_timeout_seconds}s, max_pending={max_pending_orders})"
        )

    def on_order_event(self, event: OrderEvent):
        """
        Handle order events from OMS

        Args:
            event: OrderEvent with status SUBMITTED or CANCELLED
        """
        if event.status == "SUBMITTED":
            self._handle_order_submission(event)
        elif event.status == "CANCELLED":
            self._handle_order_cancellation(event)
        # Other statuses are handled by on_order_acknowledged

    def on_order_acknowledged(self, event: OrderEvent):
        """
        Handle order acknowledgment from exchange

        Args:
            event: OrderEvent with status ACCEPTED, REJECTED, or CANCELLED
        """
        if event.status in ["ACCEPTED", "REJECTED", "CANCELLED"]:
            # Cancel timeout timer if exists
            if event.order_id in self.timeout_timers:
                self.timeout_timers[event.order_id].cancel()
                del self.timeout_timers[event.order_id]

            # Remove from pending orders
            if event.order_id in self.pending_orders:
                del self.pending_orders[event.order_id]

            if event.status == "ACCEPTED":
                self.logger.debug(f"Order acknowledged: {event.order_id[:8]}")
            elif event.status == "REJECTED":
                self.logger.warning(f"Order rejected: {event.order_id[:8]}")
            elif event.status == "CANCELLED":
                self.logger.info(f"Order cancelled: {event.order_id[:8]}")

    def _handle_order_submission(self, event: OrderEvent):
        """
        Handle order submission

        Args:
            event: OrderEvent with status SUBMITTED
        """
        # Check if we have too many pending orders
        if len(self.pending_orders) >= self.max_pending_orders:
            self.logger.warning(
                f"Too many pending orders ({len(self.pending_orders)}), "
                f"rejecting {event.order_id[:8]}"
            )
            self._reject_order(event, "Too many pending orders")
            return

        # Pre-submission risk check
        if self.risk_manager:
            if not self.risk_manager.validate_order_submission(event):
                self.logger.warning(
                    f"Order {event.order_id[:8]} rejected by risk manager"
                )
                self._reject_order(event, "Risk check failed")
                return

        # Check connection status
        if not self.connector.get_connection_status():
            self.logger.error(
                f"Cannot submit order {event.order_id[:8]}: not connected to FIX"
            )
            self._reject_order(event, "FIX connection not available")
            return

        # Submit order via FIX
        try:
            pb_order_id = self.connector.place_order(
                order_id=event.order_id,
                symbol=event.contract,
                side=event.side,
                price=float(event.price),
                quantity=event.quantity
            )

            if pb_order_id:
                # Track pending order
                self.pending_orders[event.order_id] = event

                # Set timeout timer
                timer = Timer(
                    self.order_timeout_seconds,
                    self._handle_order_timeout,
                    args=[event.order_id]
                )
                timer.start()
                self.timeout_timers[event.order_id] = timer

                self.logger.info(
                    f"Order submitted: {event.order_id[:8]} "
                    f"({event.side} {event.quantity}x{event.contract}@{event.price})"
                )
            else:
                # Submission failed
                self._reject_order(event, "Order submission failed")

        except Exception as e:
            self.logger.error(
                f"Failed to submit order {event.order_id[:8]}: {e}"
            )
            self._reject_order(event, f"Submission error: {str(e)}")

    def _handle_order_cancellation(self, event: OrderEvent):
        """
        Handle order cancellation request

        Args:
            event: OrderEvent with status CANCELLED
        """
        # Check if order is pending
        if event.order_id not in self.pending_orders:
            self.logger.warning(
                f"Cannot cancel order {event.order_id[:8]}: not in pending orders"
            )
            return

        # Send cancel request via FIX
        success = self.connector.cancel_order(event.order_id)

        if success:
            self.logger.info(f"Cancel request sent for {event.order_id[:8]}")
            # Wait for cancel confirmation from exchange
        else:
            self.logger.warning(
                f"Failed to send cancel request for {event.order_id[:8]}"
            )

    def _handle_order_timeout(self, order_id: str):
        """
        Handle order timeout (no acknowledgment received)

        Args:
            order_id: Order that timed out
        """
        if order_id in self.pending_orders:
            self.logger.error(
                f"Order timeout: {order_id[:8]} - no acknowledgment after "
                f"{self.order_timeout_seconds}s"
            )

            # Remove from pending
            order = self.pending_orders[order_id]
            del self.pending_orders[order_id]

            # Clean up timer
            if order_id in self.timeout_timers:
                del self.timeout_timers[order_id]

            # Publish rejection event
            self._reject_order(order, "Order acknowledgment timeout")

            # Try to cancel the order (in case it's stuck)
            self.connector.cancel_order(order_id)

    def _reject_order(self, order: OrderEvent, reason: str):
        """
        Reject an order and publish rejection event

        Args:
            order: Order to reject
            reason: Rejection reason
        """
        rejection_event = OrderEvent(
            order_id=order.order_id,
            contract=order.contract,
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            status="REJECTED",
            timestamp=datetime.now()
        )
        self.event_bus.publish(rejection_event)

        self.logger.warning(
            f"Order rejected: {order.order_id[:8]} - {reason}"
        )

    def get_pending_orders(self) -> Dict[str, OrderEvent]:
        """
        Get all pending orders

        Returns:
            Dictionary of pending orders
        """
        return self.pending_orders.copy()

    def get_pending_count(self) -> int:
        """
        Get count of pending orders

        Returns:
            Number of pending orders
        """
        return len(self.pending_orders)

    def is_connected(self) -> bool:
        """
        Check if connected to FIX server

        Returns:
            True if connected, False otherwise
        """
        return self.connector.get_connection_status()

    def shutdown(self):
        """Clean up resources"""
        # Cancel all timeout timers
        for timer in self.timeout_timers.values():
            timer.cancel()
        self.timeout_timers.clear()

        # Clear pending orders
        self.pending_orders.clear()

        self.logger.info("PaperBrokerExecutionEngine shutdown complete")

    def __str__(self) -> str:
        """String representation"""
        return (
            f"PaperBrokerExecutionEngine("
            f"connected={self.is_connected()}, "
            f"pending={len(self.pending_orders)})"
        )

    def __repr__(self) -> str:
        """Detailed representation"""
        return self.__str__()
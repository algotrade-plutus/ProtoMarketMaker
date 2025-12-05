"""
PaperBroker Connector

Provides integration with PaperBroker paper trading server via FIX 4.4 protocol.
Translates between PaperBroker events and ProtoMarketMaker event system.
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Optional
from threading import Lock

try:
    from paperbroker import PaperBrokerClient
except ImportError:
    raise ImportError(
        "paperbroker-client is required for PaperBroker integration. "
        "Install with: pip install paperbroker-client"
    )

from protomarketmaker.core import EventBus, OrderEvent, FillEvent, EventType


class PaperBrokerConnector:
    """
    Wrapper for PaperBrokerClient that translates between
    paperbroker-client events and ProtoMarketMaker events.

    Responsibilities:
    - Manage FIX connection lifecycle
    - Translate fix:execution_report → OrderEvent/FillEvent
    - Translate fix:order_cancel_reject → OrderEvent(REJECTED)
    - Handle reconnection on disconnect
    - Thread-safe order ID tracking

    Example:
        connector = PaperBrokerConnector(
            event_bus=event_bus,
            fix_host="fix.paperbroker.com",
            fix_port=5001,
            sender_comp_id="PMM-TRADER",
            target_comp_id="SERVER",
            username="trader001",
            password="secret",
            rest_base_url="http://api.paperbroker.com:9090",
            default_sub_account="D1"
        )

        # Connect
        if connector.connect():
            # Place order
            pb_order_id = connector.place_order(
                order_id="PMM-123",
                symbol="VN30F2511",
                side="BUY",
                price=1950.0,
                quantity=1
            )
    """

    def __init__(
        self,
        event_bus: EventBus,
        fix_host: str,
        fix_port: int,
        sender_comp_id: str,
        target_comp_id: str,
        username: str,
        password: str,
        rest_base_url: str,
        default_sub_account: str,
        fee_rate: float = 0.002  # 0.2% default
    ):
        """
        Initialize PaperBroker connector

        Args:
            event_bus: ProtoMarketMaker event bus for publishing events
            fix_host: FIX server hostname
            fix_port: FIX server port
            sender_comp_id: FIX sender ID (client)
            target_comp_id: FIX target ID (server)
            username: FIX username for authentication
            password: FIX password for authentication
            rest_base_url: REST API base URL for account queries
            default_sub_account: Default sub-account for trading
            fee_rate: Transaction fee rate (default 0.2%)
        """
        self.event_bus = event_bus
        self.logger = logging.getLogger(__name__)
        self.fee_rate = fee_rate

        # Create PaperBroker client
        self.client = PaperBrokerClient(
            default_sub_account=default_sub_account,
            username=username,
            password=password,
            socket_connect_host=fix_host,
            socket_connect_port=fix_port,
            sender_comp_id=sender_comp_id,
            target_comp_id=target_comp_id,
            rest_base_url=rest_base_url,
            console=True  # Quiet mode - we handle logging
        )

        # Order tracking (paperbroker order_id → order details dict)
        # Each entry: {pmm_order_id, symbol, side, quantity, price}
        self.order_map: Dict[str, Dict] = {}
        self.order_map_lock = Lock()

        # Track partial fill quantities
        self.partial_fills: Dict[str, int] = {}  # order_id → last_filled_qty

        # Connection state
        self.is_connected = False

        # Subscribe to paperbroker events
        self._subscribe_to_events()

        self.logger.info(f"PaperBrokerConnector initialized for {fix_host}:{fix_port}")

    def _subscribe_to_events(self):
        """Subscribe to all relevant PaperBroker events"""
        self.logger.info("Subscribing to PaperBroker events...")

        # Logon/Logout
        self.client.on("fix:logon", self._on_logon)
        self.logger.debug("  Registered: fix:logon -> _on_logon")

        self.client.on("fix:logout", self._on_logout)
        self.logger.debug("  Registered: fix:logout -> _on_logout")

        # Order lifecycle events (CORRECTED EVENT NAMES - discovered via debug logging)
        # The paperbroker-client library uses specific event names like fix:order:accepted, fix:order:filled
        # NOT a generic fix:execution_report
        # Order submission stages: submit → pending_new → accepted → filled/rejected/cancelled
        self.client.on("fix:order:submit", self._on_order_submit)
        self.logger.debug("  Registered: fix:order:submit -> _on_order_submit")

        self.client.on("fix:order:pending_new", self._on_order_pending_new)
        self.logger.debug("  Registered: fix:order:pending_new -> _on_order_pending_new")

        self.client.on("fix:order:accepted", self._on_order_accepted)
        self.logger.debug("  Registered: fix:order:accepted -> _on_order_accepted")

        self.client.on("fix:order:filled", self._on_order_filled)
        self.logger.debug("  Registered: fix:order:filled -> _on_order_filled")

        self.client.on("fix:order:partially_filled", self._on_order_partially_filled)
        self.logger.debug("  Registered: fix:order:partially_filled -> _on_order_partially_filled")

        self.client.on("fix:order:rejected", self._on_order_rejected)
        self.logger.debug("  Registered: fix:order:rejected -> _on_order_rejected")

        self.client.on("fix:order:cancelled", self._on_order_cancelled)
        self.logger.debug("  Registered: fix:order:cancelled -> _on_order_cancelled")

        # Generic order updates (informational)
        self.client.on("fix:order:update", self._on_order_update)
        self.logger.debug("  Registered: fix:order:update -> _on_order_update")

        # Rejections
        self.client.on("fix:order_cancel_reject", self._on_cancel_reject)
        self.logger.debug("  Registered: fix:order_cancel_reject -> _on_cancel_reject")

        self.client.on("fix:reject", self._on_reject)
        self.logger.debug("  Registered: fix:reject -> _on_reject")

        self.logger.info("All PaperBroker event handlers registered")

    def connect(self, timeout: int = 10) -> bool:
        """
        Connect to FIX server

        Args:
            timeout: Maximum seconds to wait for logon

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.logger.info("Connecting to PaperBroker FIX server...")
            self.client.connect()

            # Wait for logon (is_connected will be set by _on_logon event handler)
            if self.client.wait_until_logged_on(timeout=timeout):
                self.logger.info("Successfully connected to PaperBroker")
                return True
            else:
                self.logger.error(f"Failed to logon within {timeout} seconds")
                return False

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from FIX server"""
        try:
            self.logger.info("Disconnecting from PaperBroker...")
            self.client.disconnect()
            self.is_connected = False
            self.logger.info("Disconnected from PaperBroker")
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")

    def place_order(
        self,
        order_id: str,      # ProtoMarketMaker order ID
        symbol: str,        # "VN30F2511"
        side: str,          # "BUY" or "SELL"
        price: float,
        quantity: int
    ) -> Optional[str]:
        """
        Place order via FIX protocol

        Args:
            order_id: ProtoMarketMaker order ID (UUID)
            symbol: Contract symbol without exchange prefix
            side: Order side (BUY or SELL)
            price: Limit price
            quantity: Order quantity

        Returns:
            PaperBroker order ID if successful, None otherwise
        """
        if not self.is_connected:
            self.logger.error("Cannot place order: not connected")
            return None

        try:
            # Add exchange prefix for PaperBroker
            full_symbol = f"HNXDS:{symbol}"

            # Place order via FIX
            pb_order_id = self.client.place_order(
                full_symbol=full_symbol,
                side=side,
                qty=quantity,
                price=price,
                ord_type="LIMIT"
            )

            # Map IDs and store order details (thread-safe)
            with self.order_map_lock:
                self.order_map[pb_order_id] = {
                    'pmm_order_id': order_id,
                    'symbol': symbol,  # Without exchange prefix (e.g., "VN30F2511")
                    'side': side,
                    'quantity': quantity,
                    'price': price
                }
                self.partial_fills[pb_order_id] = 0

            self.logger.info(
                f"Order submitted to PaperBroker: PMM:{order_id[:8]} -> PB:{pb_order_id} | "
                f"{side} {quantity} {symbol} @ {price}"
            )
            self.logger.debug(f"Stored order details in order_map['{pb_order_id}']")

            return pb_order_id

        except Exception as e:
            self.logger.error(f"Failed to place order {order_id[:8]}: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order by ProtoMarketMaker order ID

        Args:
            order_id: ProtoMarketMaker order ID

        Returns:
            True if cancellation request sent, False otherwise
        """
        if not self.is_connected:
            self.logger.error("Cannot cancel order: not connected")
            return False

        # Find paperbroker order ID
        pb_order_id = None
        with self.order_map_lock:
            for pb_id, order_info in self.order_map.items():
                if order_info['pmm_order_id'] == order_id:
                    pb_order_id = pb_id
                    break

        if not pb_order_id:
            self.logger.warning(f"Order {order_id[:8]} not found for cancellation")
            return False

        try:
            success = self.client.cancel_order(pb_order_id)
            if success:
                self.logger.info(f"Cancel request sent for {order_id[:8]}")
            else:
                self.logger.warning(f"Cancel request failed for {order_id[:8]}")
            return success

        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id[:8]}: {e}")
            return False

    # Event translation handlers

    def _on_logon(self, session_id, **kwargs):
        """Handle FIX logon event"""
        self.is_connected = True
        self.logger.info(f"FIX session established: {session_id}")

    def _on_logout(self, session_id, reason=None, **kwargs):
        """Handle FIX logout event"""
        self.is_connected = False
        self.logger.warning(f"FIX session closed: {reason or 'Unknown reason'}")

        # TODO: Implement reconnection logic here
        # Could publish a system event to pause strategy

    def _on_order_submit(self, **kwargs):
        """Handle order submit event (informational - earliest stage)"""
        order_id = kwargs.get('cl_ord_id', kwargs.get('order_id', 'unknown'))
        self.logger.debug(f"Order submit: {order_id} | kwargs: {kwargs}")

    def _on_order_pending_new(self, **kwargs):
        """Handle order pending new event (informational - received by server)"""
        order_id = kwargs.get('cl_ord_id', kwargs.get('order_id', 'unknown'))
        self.logger.debug(f"Order pending new: {order_id} | kwargs: {kwargs}")

    def _on_order_update(self, **kwargs):
        """Handle generic order update event (informational)"""
        order_id = kwargs.get('cl_ord_id', kwargs.get('order_id', 'unknown'))
        self.logger.debug(f"Order update: {order_id} | kwargs: {kwargs}")

    def _on_order_accepted(self, order_id, **kwargs):
        """Handle order accepted (NEW status)"""
        try:
            self.logger.debug(f"Order accepted event: order_id={order_id}, kwargs={kwargs}")

            # Try to find order info
            # The order_id parameter might be either the client order ID or server order ID
            client_order_id = kwargs.get('cl_ord_id', kwargs.get('client_order_id', None))

            with self.order_map_lock:
                # Try the parameter first
                order_info = self.order_map.get(order_id)

                # If not found, try the client order ID from kwargs
                if not order_info and client_order_id:
                    self.logger.debug(f"Using client_order_id from kwargs: {client_order_id}")
                    order_info = self.order_map.get(client_order_id)

            if not order_info:
                self.logger.warning(
                    f"Unknown order accepted: order_id={order_id} | "
                    f"client_order_id={client_order_id} | "
                    f"Known orders: {list(self.order_map.keys())}"
                )
                return

            # Retrieve stored order details
            pmm_order_id = order_info['pmm_order_id']
            symbol = order_info['symbol']
            side = order_info['side']
            qty = order_info['quantity']
            price = order_info['price']

            self.logger.info(f"Order accepted: {pmm_order_id[:8]} | {side} {qty} {symbol} @ {price}")

            # Publish ACCEPTED event to ProtoMarketMaker
            event = OrderEvent(
                order_id=pmm_order_id,
                contract=symbol,
                side=side,
                price=Decimal(str(price)),
                quantity=qty,
                status="ACCEPTED",
                timestamp=datetime.now()
            )
            self.event_bus.publish(event)

        except Exception as e:
            self.logger.error(f"Exception in _on_order_accepted: {e}", exc_info=True)

    def _on_order_filled(self, order_id, filled_qty=None, filled_price=None, **kwargs):
        """Handle order filled"""
        try:
            self.logger.debug(f"Order filled event: order_id={order_id}, filled_qty={filled_qty}, filled_price={filled_price}, kwargs={kwargs}")

            # Try to find order info
            client_order_id = kwargs.get('cl_ord_id', kwargs.get('client_order_id', None))

            # Determine which order ID to use
            lookup_id = None
            with self.order_map_lock:
                # Try the parameter first
                if order_id in self.order_map:
                    lookup_id = order_id
                # If not found, try the client order ID from kwargs
                elif client_order_id and client_order_id in self.order_map:
                    self.logger.debug(f"Using client_order_id from kwargs: {client_order_id}")
                    lookup_id = client_order_id

                if not lookup_id:
                    self.logger.warning(
                        f"Unknown order filled: order_id={order_id} | "
                        f"client_order_id={client_order_id} | "
                        f"Known orders: {list(self.order_map.keys())}"
                    )
                    return

                # Retrieve stored order info
                order_info = self.order_map[lookup_id]
                last_filled = self.partial_fills.get(lookup_id, 0)

            # Extract order details from stored info
            pmm_order_id = order_info['pmm_order_id']
            symbol = order_info['symbol']
            side = order_info['side']
            total_qty = order_info['quantity']

            # Extract fill details from kwargs or parameters
            if filled_qty is None:
                filled_qty = kwargs.get('last_qty', kwargs.get('cum_qty', 1))
            if filled_price is None:
                filled_price = kwargs.get('last_px', kwargs.get('avg_px', 0))

            # Calculate incremental fill quantity
            incremental_qty = filled_qty - last_filled

            if incremental_qty > 0:
                self.logger.info(
                    f"Publishing FILL event: {pmm_order_id[:8]} | "
                    f"{incremental_qty} {symbol} @ {filled_price} | "
                    f"COMPLETE (total: {filled_qty}/{total_qty})"
                )

                # Publish FILL event to ProtoMarketMaker
                event = FillEvent(
                    order_id=pmm_order_id,
                    contract=symbol,
                    side=side,
                    fill_price=Decimal(str(filled_price)),
                    fill_quantity=incremental_qty,
                    fee=self._calculate_fee(incremental_qty, filled_price),
                    timestamp=datetime.now()
                )
                self.event_bus.publish(event)

                # Clean up order tracking
                with self.order_map_lock:
                    del self.order_map[lookup_id]
                    if lookup_id in self.partial_fills:
                        del self.partial_fills[lookup_id]

        except Exception as e:
            self.logger.error(f"Exception in _on_order_filled: {e}", exc_info=True)

    def _on_order_partially_filled(self, order_id, filled_qty=None, filled_price=None, **kwargs):
        """Handle order partially filled"""
        try:
            self.logger.debug(f"Order partially filled event: order_id={order_id}, filled_qty={filled_qty}, filled_price={filled_price}, kwargs={kwargs}")

            # Try to find order info
            client_order_id = kwargs.get('cl_ord_id', kwargs.get('client_order_id', None))

            # Determine which order ID to use
            lookup_id = None
            with self.order_map_lock:
                # Try the parameter first
                if order_id in self.order_map:
                    lookup_id = order_id
                # If not found, try the client order ID from kwargs
                elif client_order_id and client_order_id in self.order_map:
                    self.logger.debug(f"Using client_order_id from kwargs: {client_order_id}")
                    lookup_id = client_order_id

                if not lookup_id:
                    self.logger.warning(f"Unknown order partially filled: {order_id[:8]}")
                    return

                # Retrieve stored order info
                order_info = self.order_map[lookup_id]
                last_filled = self.partial_fills.get(lookup_id, 0)

            # Extract order details from stored info
            pmm_order_id = order_info['pmm_order_id']
            symbol = order_info['symbol']
            side = order_info['side']
            total_qty = order_info['quantity']

            # Extract fill details from kwargs or parameters
            if filled_qty is None:
                filled_qty = kwargs.get('last_qty', kwargs.get('cum_qty', 0))
            if filled_price is None:
                filled_price = kwargs.get('last_px', kwargs.get('avg_px', 0))

            # Calculate incremental fill quantity
            incremental_qty = filled_qty - last_filled

            if incremental_qty > 0:
                self.logger.info(
                    f"Publishing FILL event: {pmm_order_id[:8]} | "
                    f"{incremental_qty} {symbol} @ {filled_price} | "
                    f"PARTIAL (total: {filled_qty}/{total_qty})"
                )

                # Publish FILL event to ProtoMarketMaker
                event = FillEvent(
                    order_id=pmm_order_id,
                    contract=symbol,
                    side=side,
                    fill_price=Decimal(str(filled_price)),
                    fill_quantity=incremental_qty,
                    fee=self._calculate_fee(incremental_qty, filled_price),
                    timestamp=datetime.now()
                )
                self.event_bus.publish(event)

                # Update partial fill tracking
                with self.order_map_lock:
                    self.partial_fills[lookup_id] = filled_qty

        except Exception as e:
            self.logger.error(f"Exception in _on_order_partially_filled: {e}", exc_info=True)

    def _on_order_rejected(self, order_id, reason=None, **kwargs):
        """Handle order rejected"""
        try:
            self.logger.debug(f"Order rejected event: order_id={order_id}, reason={reason}, kwargs={kwargs}")

            # Try to find order info
            client_order_id = kwargs.get('cl_ord_id', kwargs.get('client_order_id', None))

            # Determine which order ID to use
            lookup_id = None
            with self.order_map_lock:
                # Try the parameter first
                if order_id in self.order_map:
                    lookup_id = order_id
                # If not found, try the client order ID from kwargs
                elif client_order_id and client_order_id in self.order_map:
                    lookup_id = client_order_id

                if not lookup_id:
                    self.logger.warning(f"Unknown order rejected: {order_id[:8]}")
                    return

                # Retrieve stored order info
                order_info = self.order_map[lookup_id]

            # Extract order details from stored info
            pmm_order_id = order_info['pmm_order_id']
            symbol = order_info['symbol']
            side = order_info['side']
            qty = order_info['quantity']
            price = order_info['price']

            self.logger.warning(f"Order rejected: {pmm_order_id[:8]} - {reason or 'No reason provided'}")

            # Publish REJECTED event to ProtoMarketMaker
            event = OrderEvent(
                order_id=pmm_order_id,
                contract=symbol,
                side=side,
                price=Decimal(str(price)),
                quantity=qty,
                status="REJECTED",
                timestamp=datetime.now()
            )
            self.event_bus.publish(event)

            # Clean up order tracking
            with self.order_map_lock:
                del self.order_map[lookup_id]
                if lookup_id in self.partial_fills:
                    del self.partial_fills[lookup_id]

        except Exception as e:
            self.logger.error(f"Exception in _on_order_rejected: {e}", exc_info=True)

    def _on_order_cancelled(self, order_id, **kwargs):
        """Handle order cancelled"""
        try:
            self.logger.debug(f"Order cancelled event: order_id={order_id}, kwargs={kwargs}")

            # Try to find order info
            client_order_id = kwargs.get('cl_ord_id', kwargs.get('client_order_id', None))

            # Determine which order ID to use
            lookup_id = None
            with self.order_map_lock:
                # Try the parameter first
                if order_id in self.order_map:
                    lookup_id = order_id
                # If not found, try the client order ID from kwargs
                elif client_order_id and client_order_id in self.order_map:
                    lookup_id = client_order_id

                if not lookup_id:
                    self.logger.warning(f"Unknown order cancelled: {order_id[:8]}")
                    return

                # Retrieve stored order info
                order_info = self.order_map[lookup_id]

            # Extract order details from stored info
            pmm_order_id = order_info['pmm_order_id']
            symbol = order_info['symbol']
            side = order_info['side']
            qty = order_info['quantity']
            price = order_info['price']

            self.logger.info(f"Order cancelled: {pmm_order_id[:8]}")

            # Publish CANCELLED event to ProtoMarketMaker
            event = OrderEvent(
                order_id=pmm_order_id,
                contract=symbol,
                side=side,
                price=Decimal(str(price)),
                quantity=qty,
                status="CANCELLED",
                timestamp=datetime.now()
            )
            self.event_bus.publish(event)

            # Clean up order tracking
            with self.order_map_lock:
                del self.order_map[lookup_id]
                if lookup_id in self.partial_fills:
                    del self.partial_fills[lookup_id]

        except Exception as e:
            self.logger.error(f"Exception in _on_order_cancelled: {e}", exc_info=True)

    def _on_cancel_reject(self, order_id, reason, **kwargs):
        """Handle cancel rejection"""
        with self.order_map_lock:
            order_info = self.order_map.get(order_id)

        if order_info:
            pmm_order_id = order_info['pmm_order_id']
            self.logger.warning(
                f"Cancel rejected for {pmm_order_id[:8]}: {reason}"
            )
        else:
            self.logger.warning(
                f"Cancel rejected for unknown order {order_id[:8]}: {reason}"
            )

    def _on_reject(self, reason, msg_type, **kwargs):
        """Handle admin message rejection"""
        self.logger.error(f"FIX admin reject: {msg_type} - {reason}")

    def _calculate_fee(self, quantity: int, price: float) -> Decimal:
        """
        Calculate transaction fee

        Args:
            quantity: Number of contracts
            price: Price per contract

        Returns:
            Fee amount (considering 100x multiplier for futures)
        """
        # Vietnamese futures have 100x multiplier
        # Fee is typically 0.2% of notional value
        notional = quantity * price * 100
        fee = notional * self.fee_rate
        return Decimal(str(fee))

    def get_pending_orders(self) -> Dict[str, Dict]:
        """
        Get all pending orders

        Returns:
            Dictionary of {pb_order_id: order_info_dict}
            where order_info_dict contains: {pmm_order_id, symbol, side, quantity, price}
        """
        with self.order_map_lock:
            return self.order_map.copy()

    def get_connection_status(self) -> bool:
        """
        Get connection status

        Returns:
            True if connected, False otherwise
        """
        return self.is_connected

    def get_account_balance(self) -> Optional[Dict]:
        """
        Get account balance via REST API

        Returns:
            Account balance dictionary or None if failed
        """
        try:
            balance = self.client.get_account_balance()
            return balance
        except Exception as e:
            self.logger.error(f"Failed to get account balance: {e}")
            return None

    def __str__(self) -> str:
        """String representation"""
        return (
            f"PaperBrokerConnector("
            f"connected={self.is_connected}, "
            f"pending_orders={len(self.order_map)})"
        )

    def __repr__(self) -> str:
        """Detailed representation"""
        return self.__str__()

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

from core.event import EventBus, OrderEvent, FillEvent
from core.enums import EventType


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
            console=False  # Quiet mode - we handle logging
        )

        # Order tracking (paperbroker order_id → ProtoMarketMaker order_id)
        self.order_map: Dict[str, str] = {}
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
        self.client.on("fix:logon", self._on_logon)
        self.client.on("fix:logout", self._on_logout)
        self.client.on("fix:execution_report", self._on_execution_report)
        self.client.on("fix:order_cancel_reject", self._on_cancel_reject)
        self.client.on("fix:reject", self._on_reject)

        self.logger.debug("Subscribed to PaperBroker events")

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

            # Wait for logon
            if self.client.wait_until_logged_on(timeout=timeout):
                self.is_connected = True
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

            # Map IDs (thread-safe)
            with self.order_map_lock:
                self.order_map[pb_order_id] = order_id
                self.partial_fills[pb_order_id] = 0

            self.logger.info(
                f"Order placed: {order_id[:8]} → {pb_order_id[:8]} "
                f"({side} {quantity}x{symbol}@{price})"
            )

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
            for pb_id, pmm_id in self.order_map.items():
                if pmm_id == order_id:
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

    def _on_execution_report(
        self,
        cl_ord_id,          # PaperBroker order ID
        status,             # "NEW", "PARTIALLY_FILLED", "FILLED", "REJECTED", "CANCELLED"
        symbol,
        side,
        qty,
        qty_filled,
        avg_price,
        text=None,          # Rejection reason or other text
        **kwargs
    ):
        """
        Translate execution report to ProtoMarketMaker events

        Status mapping:
        - NEW → OrderEvent(ACCEPTED)
        - PARTIALLY_FILLED → FillEvent (partial)
        - FILLED → FillEvent (complete)
        - REJECTED → OrderEvent(REJECTED)
        - CANCELLED → OrderEvent(CANCELLED)
        """
        # Get ProtoMarketMaker order ID
        with self.order_map_lock:
            pmm_order_id = self.order_map.get(cl_ord_id)
            last_filled = self.partial_fills.get(cl_ord_id, 0)

        if not pmm_order_id:
            self.logger.warning(f"Unknown order in execution report: {cl_ord_id[:8]}")
            return

        # Extract contract symbol (remove exchange prefix)
        contract = symbol.split(":")[-1] if ":" in symbol else symbol

        self.logger.debug(
            f"Execution report: {cl_ord_id[:8]} status={status} "
            f"filled={qty_filled}/{qty} price={avg_price}"
        )

        if status == "NEW":
            # Order accepted by exchange
            event = OrderEvent(
                order_id=pmm_order_id,
                contract=contract,
                side=side,
                price=Decimal(str(avg_price)) if avg_price else Decimal("0"),
                quantity=qty,
                status="ACCEPTED",
                timestamp=datetime.now()
            )
            self.event_bus.publish(event)
            self.logger.info(f"Order accepted: {pmm_order_id[:8]}")

        elif status in ["PARTIALLY_FILLED", "FILLED"]:
            # Calculate incremental fill quantity
            incremental_qty = qty_filled - last_filled

            if incremental_qty > 0:
                # Order filled (partial or complete)
                event = FillEvent(
                    order_id=pmm_order_id,
                    contract=contract,
                    side=side,
                    fill_price=Decimal(str(avg_price)),
                    fill_quantity=incremental_qty,  # Only the new fill
                    fee=self._calculate_fee(incremental_qty, avg_price),
                    timestamp=datetime.now()
                )
                self.event_bus.publish(event)

                # Update partial fill tracking
                with self.order_map_lock:
                    self.partial_fills[cl_ord_id] = qty_filled

                self.logger.info(
                    f"Order {'filled' if status == 'FILLED' else 'partially filled'}: "
                    f"{pmm_order_id[:8]} {incremental_qty}@{avg_price} "
                    f"(total: {qty_filled}/{qty})"
                )

                # Clean up if fully filled
                if status == "FILLED":
                    with self.order_map_lock:
                        del self.order_map[cl_ord_id]
                        del self.partial_fills[cl_ord_id]

        elif status == "REJECTED":
            # Order rejected
            event = OrderEvent(
                order_id=pmm_order_id,
                contract=contract,
                side=side,
                price=Decimal(str(avg_price)) if avg_price else Decimal("0"),
                quantity=qty,
                status="REJECTED",
                timestamp=datetime.now()
            )
            self.event_bus.publish(event)

            # Clean up mapping
            with self.order_map_lock:
                del self.order_map[cl_ord_id]
                if cl_ord_id in self.partial_fills:
                    del self.partial_fills[cl_ord_id]

            self.logger.warning(
                f"Order rejected: {pmm_order_id[:8]} - {text or 'No reason provided'}"
            )

        elif status == "CANCELLED":
            # Order cancelled
            event = OrderEvent(
                order_id=pmm_order_id,
                contract=contract,
                side=side,
                price=Decimal(str(avg_price)) if avg_price else Decimal("0"),
                quantity=qty,
                status="CANCELLED",
                timestamp=datetime.now()
            )
            self.event_bus.publish(event)

            # Clean up mapping
            with self.order_map_lock:
                del self.order_map[cl_ord_id]
                if cl_ord_id in self.partial_fills:
                    del self.partial_fills[cl_ord_id]

            self.logger.info(f"Order cancelled: {pmm_order_id[:8]}")

    def _on_cancel_reject(self, order_id, reason, **kwargs):
        """Handle cancel rejection"""
        with self.order_map_lock:
            pmm_order_id = self.order_map.get(order_id)

        if pmm_order_id:
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

    def get_pending_orders(self) -> Dict[str, str]:
        """
        Get all pending orders

        Returns:
            Dictionary of {pb_order_id: pmm_order_id}
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
"""
Unit tests for PaperBrokerConnector

Tests event translation, order management, and connection handling
without requiring a live FIX connection.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from decimal import Decimal
from datetime import datetime
from threading import Lock

from connectors.paperbroker_connector import PaperBrokerConnector
from core.event import EventBus, FillEvent, OrderEvent
from core.enums import EventType


class TestPaperBrokerConnector:
    """Test suite for PaperBrokerConnector"""

    @pytest.fixture
    def event_bus(self):
        """Create event bus fixture"""
        return EventBus()

    @pytest.fixture
    def mock_client(self):
        """Create mock PaperBrokerClient"""
        mock = Mock()
        mock.connect = Mock(return_value=None)
        mock.wait_until_logged_on = Mock(return_value=True)
        mock.disconnect = Mock(return_value=None)
        mock.place_order = Mock(return_value="PB_ORDER_123")
        mock.cancel_order = Mock(return_value=True)
        mock.on = Mock()  # For event subscription
        return mock

    @pytest.fixture
    def connector(self, event_bus):
        """Create connector with mocked client"""
        with patch('connectors.paperbroker_connector.PaperBrokerClient') as MockClient:
            mock_instance = Mock()
            mock_instance.on = Mock()
            MockClient.return_value = mock_instance

            connector = PaperBrokerConnector(
                event_bus=event_bus,
                fix_host="test.host",
                fix_port=5001,
                sender_comp_id="TEST_SENDER",
                target_comp_id="TEST_TARGET",
                username="test_user",
                password="test_pass",
                rest_base_url="http://test.api",
                default_sub_account="D1"
            )
            connector.client = mock_instance
            return connector

    def test_initialization(self, event_bus):
        """Test connector initialization"""
        with patch('connectors.paperbroker_connector.PaperBrokerClient') as MockClient:
            mock_instance = Mock()
            mock_instance.on = Mock()
            MockClient.return_value = mock_instance

            connector = PaperBrokerConnector(
                event_bus=event_bus,
                fix_host="test.host",
                fix_port=5001,
                sender_comp_id="SENDER",
                target_comp_id="TARGET",
                username="user",
                password="pass",
                rest_base_url="http://api",
                default_sub_account="D1",
                fee_rate=0.002
            )

            # Verify client was created with correct parameters
            MockClient.assert_called_once()
            assert connector.event_bus == event_bus
            assert connector.fee_rate == 0.002
            assert not connector.is_connected
            assert len(connector.order_map) == 0

            # Verify event subscriptions
            assert mock_instance.on.call_count >= 5  # At least 5 event types

    def test_connect_success(self, connector):
        """Test successful connection"""
        connector.client.connect = Mock(return_value=None)
        connector.client.wait_until_logged_on = Mock(return_value=True)

        result = connector.connect(timeout=10)

        assert result is True
        assert connector.is_connected is False  # Set by logon event
        connector.client.connect.assert_called_once()
        connector.client.wait_until_logged_on.assert_called_with(timeout=10)

    def test_connect_failure(self, connector):
        """Test failed connection"""
        connector.client.connect = Mock(return_value=None)
        connector.client.wait_until_logged_on = Mock(return_value=False)

        result = connector.connect(timeout=5)

        assert result is False
        assert not connector.is_connected

    def test_disconnect(self, connector):
        """Test disconnection"""
        connector.is_connected = True
        connector.client.disconnect = Mock(return_value=None)

        connector.disconnect()

        assert not connector.is_connected
        connector.client.disconnect.assert_called_once()

    def test_place_order_success(self, connector):
        """Test successful order placement - stores order details as dict"""
        connector.is_connected = True
        connector.client.place_order = Mock(return_value="PB_123")

        pb_order_id = connector.place_order(
            order_id="PMM_456",
            symbol="VN30F2511",
            side="BUY",
            price=1950.0,
            quantity=1
        )

        assert pb_order_id == "PB_123"
        # Verify order_map stores dict with order details
        assert connector.order_map["PB_123"]["pmm_order_id"] == "PMM_456"
        assert connector.order_map["PB_123"]["symbol"] == "VN30F2511"
        assert connector.order_map["PB_123"]["side"] == "BUY"
        assert connector.order_map["PB_123"]["quantity"] == 1
        assert connector.order_map["PB_123"]["price"] == 1950.0
        assert connector.partial_fills["PB_123"] == 0

        connector.client.place_order.assert_called_once_with(
            full_symbol="HNXDS:VN30F2511",
            side="BUY",
            qty=1,
            price=1950.0,
            ord_type="LIMIT"
        )

    def test_place_order_not_connected(self, connector):
        """Test order placement when not connected"""
        connector.is_connected = False

        result = connector.place_order(
            order_id="PMM_456",
            symbol="VN30F2511",
            side="BUY",
            price=1950.0,
            quantity=1
        )

        assert result is None
        assert len(connector.order_map) == 0

    def test_cancel_order_success(self, connector):
        """Test successful order cancellation - finds order by pmm_order_id"""
        connector.is_connected = True
        connector.order_map["PB_123"] = {
            'pmm_order_id': "PMM_456",
            'symbol': "VN30F2511",
            'side': "BUY",
            'quantity': 1,
            'price': 1950.0
        }
        connector.client.cancel_order = Mock(return_value=True)

        result = connector.cancel_order("PMM_456")

        assert result is True
        connector.client.cancel_order.assert_called_once_with("PB_123")

    def test_cancel_order_not_found(self, connector):
        """Test cancellation of unknown order"""
        connector.is_connected = True

        result = connector.cancel_order("UNKNOWN_ORDER")

        assert result is False
        connector.client.cancel_order.assert_not_called()

    def test_order_accepted_event(self, connector, event_bus):
        """Test order accepted event - retrieves stored order details"""
        connector.order_map["PB_123"] = {
            'pmm_order_id': "PMM_456",
            'symbol': "VN30F2511",
            'side': "BUY",
            'quantity': 10,
            'price': 1950.0
        }
        captured_events = []

        def capture(event):
            captured_events.append(event)

        event_bus.subscribe(EventType.ORDER, capture)

        # Simulate order accepted event (using cl_ord_id in kwargs)
        connector._on_order_accepted(
            order_id="SERVER_ORDER_ID",  # Server may use different ID
            cl_ord_id="PB_123"  # Our client order ID is in kwargs
        )

        # Process events
        event_bus.process_events()

        assert len(captured_events) == 1
        order_event = captured_events[0]
        assert order_event.order_id == "PMM_456"
        assert order_event.status == "ACCEPTED"
        assert order_event.contract == "VN30F2511"
        assert order_event.side == "BUY"
        assert order_event.quantity == 10

    def test_order_filled_event(self, connector, event_bus):
        """Test order filled event - retrieves stored order details for FillEvent"""
        connector.order_map["PB_123"] = {
            'pmm_order_id': "PMM_456",
            'symbol': "VN30F2511",
            'side': "BUY",
            'quantity': 10,
            'price': 1950.0
        }
        connector.partial_fills["PB_123"] = 0
        captured_events = []

        def capture(event):
            captured_events.append(event)

        event_bus.subscribe(EventType.FILL, capture)

        # Simulate filled event (kwargs contain cl_ord_id and fill details)
        connector._on_order_filled(
            order_id="SERVER_ORDER_ID",
            cl_ord_id="PB_123",
            last_qty=10,
            last_px=1950.0
        )

        # Process events
        event_bus.process_events()

        assert len(captured_events) == 1
        fill_event = captured_events[0]
        assert fill_event.order_id == "PMM_456"
        assert fill_event.fill_quantity == 10
        assert fill_event.fill_price == Decimal("1950.0")
        assert fill_event.contract == "VN30F2511"
        assert fill_event.side == "BUY"

        # Order should be removed from maps
        assert "PB_123" not in connector.order_map
        assert "PB_123" not in connector.partial_fills

    def test_partial_fill_tracking(self, connector, event_bus):
        """Test partial fill incremental quantity calculation"""
        connector.order_map["PB_123"] = {
            'pmm_order_id': "PMM_456",
            'symbol': "VN30F2511",
            'side': "BUY",
            'quantity': 10,
            'price': 1950.0
        }
        connector.partial_fills["PB_123"] = 0
        captured_events = []

        def capture(event):
            captured_events.append(event)

        event_bus.subscribe(EventType.FILL, capture)

        # First partial fill (3 contracts)
        connector._on_order_partially_filled(
            order_id="SERVER_ID",
            cl_ord_id="PB_123",
            last_qty=3,
            last_px=1950.0
        )
        event_bus.process_events()

        # Second partial fill (5 total)
        connector._on_order_partially_filled(
            order_id="SERVER_ID",
            cl_ord_id="PB_123",
            last_qty=5,
            last_px=1950.0
        )
        event_bus.process_events()

        # Final fill (10 total)
        connector._on_order_filled(
            order_id="SERVER_ID",
            cl_ord_id="PB_123",
            last_qty=10,
            last_px=1950.0
        )
        event_bus.process_events()

        assert len(captured_events) == 3

        # First partial: 3 contracts
        assert captured_events[0].fill_quantity == 3

        # Second partial: 2 incremental (5 - 3)
        assert captured_events[1].fill_quantity == 2

        # Final fill: 5 incremental (10 - 5)
        assert captured_events[2].fill_quantity == 5

        # Order should be cleaned up after final fill
        assert "PB_123" not in connector.order_map
        assert "PB_123" not in connector.partial_fills

    def test_order_rejected_event(self, connector, event_bus):
        """Test order rejected event - cleans up order_map"""
        connector.order_map["PB_123"] = {
            'pmm_order_id': "PMM_456",
            'symbol': "VN30F2511",
            'side': "BUY",
            'quantity': 10,
            'price': 1950.0
        }
        captured_events = []

        def capture(event):
            captured_events.append(event)

        event_bus.subscribe(EventType.ORDER, capture)

        # Simulate rejected event
        connector._on_order_rejected(
            order_id="SERVER_ID",
            reason="Insufficient margin",
            cl_ord_id="PB_123"
        )

        # Process events
        event_bus.process_events()

        assert len(captured_events) == 1
        order_event = captured_events[0]
        assert order_event.order_id == "PMM_456"
        assert order_event.status == "REJECTED"

        # Order should be removed from maps
        assert "PB_123" not in connector.order_map

    def test_fee_calculation(self, connector):
        """Test fee calculation"""
        # Vietnamese futures: 100x multiplier, 0.2% fee
        fee = connector._calculate_fee(quantity=10, price=1950.0)

        # Fee = 10 * 1950 * 100 * 0.002 = 3900
        assert fee == Decimal("3900")

    def test_on_logon(self, connector):
        """Test logon event handling"""
        connector._on_logon(session_id="FIX.4.4:SENDER->TARGET")

        assert connector.is_connected is True

    def test_on_logout(self, connector):
        """Test logout event handling"""
        connector.is_connected = True

        connector._on_logout(
            session_id="FIX.4.4:SENDER->TARGET",
            reason="User requested disconnect"
        )

        assert connector.is_connected is False

    def test_thread_safety(self, connector):
        """Test thread-safe order map operations"""
        # Verify lock is used for order map
        assert isinstance(connector.order_map_lock, Lock)

        # Test concurrent access (would normally use threading)
        with connector.order_map_lock:
            connector.order_map["PB_1"] = {
                'pmm_order_id': "PMM_1",
                'symbol': "VN30F2511",
                'side': "BUY",
                'quantity': 1,
                'price': 1950.0
            }
            assert connector.order_map["PB_1"]["pmm_order_id"] == "PMM_1"

    def test_order_cancelled_event(self, connector, event_bus):
        """Test order cancelled event - cleans up order_map"""
        connector.order_map["PB_123"] = {
            'pmm_order_id': "PMM_456",
            'symbol': "VN30F2511",
            'side': "BUY",
            'quantity': 10,
            'price': 1950.0
        }
        captured_events = []

        def capture(event):
            captured_events.append(event)

        event_bus.subscribe(EventType.ORDER, capture)

        # Simulate cancelled event
        connector._on_order_cancelled(
            order_id="SERVER_ID",
            cl_ord_id="PB_123"
        )

        # Process events
        event_bus.process_events()

        assert len(captured_events) == 1
        order_event = captured_events[0]
        assert order_event.order_id == "PMM_456"
        assert order_event.status == "CANCELLED"

        # Order should be removed from maps
        assert "PB_123" not in connector.order_map

    def test_unknown_order_handling(self, connector, event_bus):
        """Test graceful handling of unknown order IDs"""
        captured_events = []

        def capture(event):
            captured_events.append(event)

        event_bus.subscribe(EventType.ORDER, capture)
        event_bus.subscribe(EventType.FILL, capture)

        # These should not raise exceptions or publish events
        connector._on_order_accepted(order_id="UNKNOWN_ID", cl_ord_id="ALSO_UNKNOWN")
        connector._on_order_filled(order_id="UNKNOWN_ID", cl_ord_id="ALSO_UNKNOWN")
        connector._on_order_cancelled(order_id="UNKNOWN_ID", cl_ord_id="ALSO_UNKNOWN")

        # Process events
        event_bus.process_events()

        # No events should be published for unknown orders
        assert len(captured_events) == 0
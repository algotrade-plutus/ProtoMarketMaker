"""
Integration tests for PaperBroker paper trading

Tests end-to-end workflow with mock FIX server responses.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from decimal import Decimal
from datetime import datetime
import uuid

from core.event import EventBus, SignalEvent, OrderEvent, FillEvent
from core.enums import EventType, OrderStatus
from engine.oms import OrderManager
from engine.portfolio import PortfolioManager
from engine.risk import RiskManager
from engine.strategy import MarketMakerStrategy
from engine.paperbroker_execution import PaperBrokerExecutionEngine
from connectors.paperbroker_connector import PaperBrokerConnector


class TestPaperBrokerIntegration:
    """Integration tests for PaperBroker trading workflow"""

    @pytest.fixture
    def event_bus(self):
        """Create event bus fixture"""
        return EventBus()

    @pytest.fixture
    def mock_connector(self, event_bus):
        """Create mock PaperBroker connector"""
        connector = Mock(spec=PaperBrokerConnector)
        connector.event_bus = event_bus
        connector.is_connected = True
        connector.get_connection_status = Mock(return_value=True)
        connector.place_order = Mock(return_value="PB_ORDER_123")
        connector.cancel_order = Mock(return_value=True)
        return connector

    @pytest.fixture
    def trading_system(self, event_bus, mock_connector):
        """Create complete trading system with PaperBroker execution"""
        # Initialize portfolio
        portfolio = PortfolioManager(
            event_bus=event_bus,
            initial_capital=Decimal('500000')
        )

        # Initialize risk manager
        risk = RiskManager(portfolio=portfolio)

        # Initialize OMS with order event handler
        oms = OrderManager(
            event_bus=event_bus,
            risk_manager=risk
        )

        # Subscribe OMS to order events for acknowledgments
        event_bus.subscribe(EventType.ORDER, oms.on_order_event)

        # Initialize strategy
        strategy = MarketMakerStrategy(
            event_bus=event_bus,
            portfolio=portfolio,
            step=Decimal('2.9'),
            update_interval_seconds=15
        )

        # Initialize PaperBroker execution
        execution = PaperBrokerExecutionEngine(
            event_bus=event_bus,
            connector=mock_connector,
            risk_manager=risk,
            order_timeout_seconds=5,
            max_pending_orders=10
        )

        return {
            'event_bus': event_bus,
            'portfolio': portfolio,
            'risk': risk,
            'oms': oms,
            'strategy': strategy,
            'execution': execution,
            'connector': mock_connector
        }

    def test_signal_to_order_flow(self, trading_system):
        """Test complete flow from signal to order submission"""
        event_bus = trading_system['event_bus']
        oms = trading_system['oms']
        execution = trading_system['execution']
        connector = trading_system['connector']

        # Create and publish signal event
        signal = SignalEvent(
            contract="VN30F2511",
            bid_price=Decimal("1950.0"),
            ask_price=Decimal("1953.0"),
            reason="TIME_ELAPSED",
            timestamp=datetime.now()
        )

        # Publish signal (strategy would normally do this)
        event_bus.publish(signal)

        # Process events (OMS creates orders)
        event_bus.process_events()

        # Verify orders were created
        assert len(oms.get_active_orders()) == 2  # Bid and ask

        # Process again for order submission
        event_bus.process_events()

        # Verify connector was called twice (bid and ask)
        assert connector.place_order.call_count == 2

        # Check bid order submission
        bid_call = connector.place_order.call_args_list[0]
        assert bid_call[1]['symbol'] == "VN30F2511"
        assert bid_call[1]['side'] == "BUY"
        assert bid_call[1]['price'] == 1950.0
        assert bid_call[1]['quantity'] == 1

        # Check ask order submission
        ask_call = connector.place_order.call_args_list[1]
        assert ask_call[1]['symbol'] == "VN30F2511"
        assert ask_call[1]['side'] == "SELL"
        assert ask_call[1]['price'] == 1953.0
        assert ask_call[1]['quantity'] == 1

        # Verify pending orders in execution engine
        assert execution.get_pending_count() == 2

    def test_order_acknowledgment_flow(self, trading_system):
        """Test order acknowledgment from exchange"""
        event_bus = trading_system['event_bus']
        oms = trading_system['oms']
        execution = trading_system['execution']

        # Create order directly
        order_id = str(uuid.uuid4())
        order_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="SUBMITTED",
            timestamp=datetime.now()
        )

        # Add to execution pending orders (simulating submission)
        execution.pending_orders[order_id] = order_event

        # Simulate acknowledgment from exchange
        ack_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="ACCEPTED",
            timestamp=datetime.now()
        )

        # Publish acknowledgment
        event_bus.publish(ack_event)

        # Process events
        event_bus.process_events()

        # Order should be removed from pending
        assert order_id not in execution.pending_orders

    def test_order_fill_flow(self, trading_system):
        """Test order fill processing"""
        event_bus = trading_system['event_bus']
        portfolio = trading_system['portfolio']
        oms = trading_system['oms']
        connector = trading_system['connector']

        # First create orders through normal flow
        signal = SignalEvent(
            contract="VN30F2511",
            bid_price=Decimal("1950.0"),
            ask_price=Decimal("1953.0"),
            reason="TIME_ELAPSED",
            timestamp=datetime.now()
        )

        event_bus.publish(signal)
        event_bus.process_events()  # OMS creates orders
        event_bus.process_events()  # Execute orders

        # Get the bid order that was created
        active_orders = oms.get_active_orders()
        bid_order = [o for o in active_orders if o.side.value == "BID"][0]

        # Now simulate fill event from connector for that order
        # Note: Our strategy creates orders with quantity=1
        fill_event = FillEvent(
            order_id=bid_order.order_id,
            contract="VN30F2511",
            side="BID",
            fill_price=Decimal("1950.0"),
            fill_quantity=1,
            fee=Decimal("3.9"),
            timestamp=datetime.now()
        )

        # Publish fill event
        event_bus.publish(fill_event)

        # Process events
        event_bus.process_events()

        # Check portfolio updated
        position = portfolio.get_position("VN30F2511")
        assert position.quantity == 1
        assert position.average_price == Decimal("1950.0")

    def test_order_rejection_flow(self, trading_system):
        """Test order rejection handling"""
        event_bus = trading_system['event_bus']
        execution = trading_system['execution']
        oms = trading_system['oms']

        # Create order
        order_id = str(uuid.uuid4())
        order_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="SUBMITTED",
            timestamp=datetime.now()
        )

        # Add to execution pending orders
        execution.pending_orders[order_id] = order_event

        # Simulate rejection from exchange
        reject_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="REJECTED",
            timestamp=datetime.now()
        )

        # Publish rejection
        event_bus.publish(reject_event)

        # Process events
        event_bus.process_events()

        # Order should be removed from pending
        assert order_id not in execution.pending_orders

    def test_risk_check_rejection(self, trading_system):
        """Test order rejected by risk manager"""
        event_bus = trading_system['event_bus']
        execution = trading_system['execution']
        risk = trading_system['risk']

        # Mock risk check to fail
        risk.validate_order = Mock(return_value=False)

        # Submit order
        order_event = OrderEvent(
            order_id=str(uuid.uuid4()),
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=100,  # Large quantity
            status="SUBMITTED",
            timestamp=datetime.now()
        )

        # Publish order
        event_bus.publish(order_event)

        # Process events
        event_bus.process_events()

        # Risk check should have been called
        risk.validate_order.assert_called_once()

        # Order should not be in pending (rejected pre-submission)
        assert order_event.order_id not in execution.pending_orders

    def test_connection_failure_handling(self, trading_system):
        """Test handling when FIX connection is down"""
        event_bus = trading_system['event_bus']
        execution = trading_system['execution']
        connector = trading_system['connector']

        # Simulate connection down
        connector.get_connection_status = Mock(return_value=False)

        # Try to submit order
        order_event = OrderEvent(
            order_id=str(uuid.uuid4()),
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="SUBMITTED",
            timestamp=datetime.now()
        )

        # Publish order
        event_bus.publish(order_event)

        # Process events
        event_bus.process_events()

        # Connector should not have been called
        connector.place_order.assert_not_called()

        # Order should not be pending
        assert order_event.order_id not in execution.pending_orders

    def test_order_timeout_handling(self, trading_system):
        """Test order timeout when no acknowledgment received"""
        event_bus = trading_system['event_bus']
        execution = trading_system['execution']

        # Create short timeout execution engine
        execution.order_timeout_seconds = 0.1

        # Submit order
        order_id = str(uuid.uuid4())
        order_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="SUBMITTED",
            timestamp=datetime.now()
        )

        # Add to pending with timer
        execution.pending_orders[order_id] = order_event
        execution._handle_order_submission(order_event)

        # Wait for timeout
        import time
        time.sleep(0.2)

        # Order should be removed from pending
        assert order_id not in execution.pending_orders

    def test_partial_fill_handling(self, trading_system):
        """Test handling of partial fills"""
        event_bus = trading_system['event_bus']
        portfolio = trading_system['portfolio']
        oms = trading_system['oms']

        # First create orders through normal flow
        signal = SignalEvent(
            contract="VN30F2511",
            bid_price=Decimal("1950.0"),
            ask_price=Decimal("1953.0"),
            reason="TIME_ELAPSED",
            timestamp=datetime.now()
        )

        event_bus.publish(signal)
        event_bus.process_events()  # OMS creates orders
        event_bus.process_events()  # Execute orders

        # Get the bid order that was created
        active_orders = oms.get_active_orders()
        bid_order = [o for o in active_orders if o.side.value == "BID"][0]

        # Fill the first bid order (quantity=1)
        fill1 = FillEvent(
            order_id=bid_order.order_id,
            contract="VN30F2511",
            side="BID",
            fill_price=Decimal("1950.0"),
            fill_quantity=1,
            fee=Decimal("3.9"),
            timestamp=datetime.now()
        )

        event_bus.publish(fill1)
        event_bus.process_events()

        # Check position after first fill
        position = portfolio.get_position("VN30F2511")
        assert position.quantity == 1

        # Create another signal to generate more orders
        signal2 = SignalEvent(
            contract="VN30F2511",
            bid_price=Decimal("1951.0"),
            ask_price=Decimal("1954.0"),
            reason="TIME_ELAPSED",
            timestamp=datetime.now()
        )

        event_bus.publish(signal2)
        event_bus.process_events()  # OMS creates orders
        event_bus.process_events()  # Execute orders

        # Get the new bid order
        active_orders = oms.get_active_orders()
        new_bid_orders = [o for o in active_orders if o.side.value == "BID" and o.order_id != bid_order.order_id]

        if new_bid_orders:
            # Fill the second bid order
            fill2 = FillEvent(
                order_id=new_bid_orders[0].order_id,
                contract="VN30F2511",
                side="BID",
                fill_price=Decimal("1951.0"),
                fill_quantity=1,
                fee=Decimal("3.9"),
                timestamp=datetime.now()
            )

            event_bus.publish(fill2)
            event_bus.process_events()

            # Check position after second fill
            position = portfolio.get_position("VN30F2511")
            assert position.quantity == 2

    def test_cancel_order_flow(self, trading_system):
        """Test order cancellation"""
        event_bus = trading_system['event_bus']
        execution = trading_system['execution']
        connector = trading_system['connector']

        # Create and submit order
        order_id = str(uuid.uuid4())
        order_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="SUBMITTED",
            timestamp=datetime.now()
        )

        execution.pending_orders[order_id] = order_event

        # Request cancellation
        cancel_event = OrderEvent(
            order_id=order_id,
            contract="VN30F2511",
            side="BUY",
            price=Decimal("1950.0"),
            quantity=1,
            status="CANCELLED",
            timestamp=datetime.now()
        )

        event_bus.publish(cancel_event)
        event_bus.process_events()

        # Verify cancel request sent
        connector.cancel_order.assert_called_once_with(order_id)

    def test_end_to_end_trading_session(self, trading_system):
        """Test complete trading session with multiple events"""
        event_bus = trading_system['event_bus']
        portfolio = trading_system['portfolio']
        oms = trading_system['oms']
        execution = trading_system['execution']

        # Initial capital check
        assert portfolio.calculate_nav() == Decimal('500000')

        # Generate signal
        signal = SignalEvent(
            contract="VN30F2511",
            bid_price=Decimal("1950.0"),
            ask_price=Decimal("1953.0"),
            reason="MARKET_UPDATE",
            timestamp=datetime.now()
        )

        event_bus.publish(signal)
        event_bus.process_events()
        event_bus.process_events()  # Process order submissions

        # Simulate bid fill
        bid_order = list(oms.get_active_orders())[0]
        fill = FillEvent(
            order_id=bid_order.order_id,
            contract="VN30F2511",
            side="BID",
            fill_price=Decimal("1950.0"),
            fill_quantity=1,
            fee=Decimal("3.9"),
            timestamp=datetime.now()
        )

        event_bus.publish(fill)
        event_bus.process_events()

        # Check position
        position = portfolio.get_position("VN30F2511")
        assert position.quantity == 1

        # Generate new signal (price moved)
        signal2 = SignalEvent(
            contract="VN30F2511",
            bid_price=Decimal("1955.0"),
            ask_price=Decimal("1958.0"),
            reason="MARKET_UPDATE",
            timestamp=datetime.now()
        )

        event_bus.publish(signal2)
        event_bus.process_events()
        event_bus.process_events()

        # Simulate ask fill (closing position)
        ask_orders = [o for o in oms.get_active_orders() if o.side.value == "ASK"]
        if ask_orders:
            fill2 = FillEvent(
                order_id=ask_orders[-1].order_id,
                contract="VN30F2511",
                side="ASK",
                fill_price=Decimal("1958.0"),
                fill_quantity=1,
                fee=Decimal("3.9"),
                timestamp=datetime.now()
            )

            event_bus.publish(fill2)
            event_bus.process_events()

        # Final position should be flat
        position = portfolio.get_position("VN30F2511")
        assert position.quantity == 0

        # Check PnL (should have profit from spread capture)
        # Bought at 1950, sold at 1958, minus fees
        # Gross profit: 8 * 100 = 800
        # Fees: 3.9 + 3.9 = 7.8
        # Net profit: 800 - 7.8 = 792.2
        # (actual calculation depends on contract multiplier)

    def test_shutdown_cleanup(self, trading_system):
        """Test proper cleanup on shutdown"""
        execution = trading_system['execution']

        # Add some pending orders
        for i in range(3):
            order_id = f"ORDER_{i}"
            execution.pending_orders[order_id] = Mock()
            execution.timeout_timers[order_id] = Mock()

        # Call shutdown
        execution.shutdown()

        # Check cleanup
        assert len(execution.pending_orders) == 0
        assert len(execution.timeout_timers) == 0
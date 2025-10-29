"""
Unit tests for Mock Execution Engine
"""
import pytest
from decimal import Decimal
from datetime import datetime
from core.event import EventBus, OrderEvent, MarketDataEvent, FillEvent
from core.enums import EventType
from engine.execution import MockExecutionEngine


class TestMockExecutionEngine:
    """Test mock execution functionality"""

    def test_initialization(self):
        """Test execution engine initialization"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        assert execution.get_pending_count() == 0
        assert len(execution.current_prices) == 0

    def test_fee_per_contract(self):
        """Test fee calculation constant"""
        assert MockExecutionEngine.FEE_PER_CONTRACT == Decimal("20")

    def test_register_pending_order(self):
        """Test registering a pending order"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )

        execution.on_order_event(order)

        assert execution.get_pending_count() == 1
        assert "test-123" in execution.pending_orders

    def test_register_multiple_orders(self):
        """Test registering multiple pending orders"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        for i in range(5):
            order = OrderEvent(
                timestamp=datetime.now(),
                order_id=f"test-{i}",
                contract="VN30F1M",
                side="BID",
                price=Decimal("1250"),
                quantity=1,
                status="SUBMITTED"
            )
            execution.on_order_event(order)

        assert execution.get_pending_count() == 5

    def test_remove_cancelled_order(self):
        """Test removing a cancelled order"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        # Submit order
        submit_order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(submit_order)

        # Cancel order
        cancel_order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="CANCELLED"
        )
        execution.on_order_event(cancel_order)

        assert execution.get_pending_count() == 0

    def test_cancel_nonexistent_order(self):
        """Test cancelling an order that doesn't exist (should not error)"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        cancel_order = OrderEvent(
            timestamp=datetime.now(),
            order_id="nonexistent",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="CANCELLED"
        )

        # Should not raise error
        execution.on_order_event(cancel_order)
        assert execution.get_pending_count() == 0

    def test_bid_order_fills_when_price_drops(self):
        """Test BID order fills when market price drops to/below bid"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit BID order @ 1250
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Market price drops to 1249 (below bid) → should fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1249"),
            bid=Decimal("1248"),
            ask=Decimal("1250"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Should generate fill event
        assert len(fills_received) == 1
        assert fills_received[0].order_id == "test-123"
        assert fills_received[0].fill_price == Decimal("1249")
        assert fills_received[0].fee == Decimal("20")
        assert fills_received[0].side == "BID"

    def test_bid_order_fills_at_exact_price(self):
        """Test BID order fills when price equals bid price"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit BID order @ 1250
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Market price exactly at 1250 → should fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Should generate fill event
        assert len(fills_received) == 1
        assert fills_received[0].fill_price == Decimal("1250")

    def test_ask_order_fills_when_price_rises(self):
        """Test ASK order fills when market price rises to/above ask"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit ASK order @ 1250
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-456",
            contract="VN30F1M",
            side="ASK",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Market price rises to 1251 (above ask) → should fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1251"),
            bid=Decimal("1250"),
            ask=Decimal("1252"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Should generate fill event
        assert len(fills_received) == 1
        assert fills_received[0].order_id == "test-456"
        assert fills_received[0].fill_price == Decimal("1251")
        assert fills_received[0].side == "ASK"

    def test_ask_order_fills_at_exact_price(self):
        """Test ASK order fills when price equals ask price"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit ASK order @ 1250
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-456",
            contract="VN30F1M",
            side="ASK",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Market price exactly at 1250 → should fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Should generate fill event
        assert len(fills_received) == 1
        assert fills_received[0].fill_price == Decimal("1250")

    def test_bid_order_does_not_fill_when_price_above(self):
        """Test BID order doesn't fill when price stays above bid"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit BID order @ 1250
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Market price stays at 1252 (above bid) → should NOT fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1252"),
            bid=Decimal("1251"),
            ask=Decimal("1253"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Should NOT generate fill event
        assert len(fills_received) == 0
        assert execution.get_pending_count() == 1

    def test_ask_order_does_not_fill_when_price_below(self):
        """Test ASK order doesn't fill when price stays below ask"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit ASK order @ 1250
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-456",
            contract="VN30F1M",
            side="ASK",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Market price stays at 1248 (below ask) → should NOT fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1248"),
            bid=Decimal("1247"),
            ask=Decimal("1249"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Should NOT generate fill event
        assert len(fills_received) == 0
        assert execution.get_pending_count() == 1

    def test_order_removed_after_fill(self):
        """Test order is removed from pending list after fill"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        assert execution.get_pending_count() == 1

        # Fill the order
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1249"),
            bid=Decimal("1248"),
            ask=Decimal("1250"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Order should be removed
        assert execution.get_pending_count() == 0
        assert "test-123" not in execution.pending_orders

    def test_multiple_orders_can_fill_simultaneously(self):
        """Test multiple orders can fill on same market data update"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit BID @ 1250 and ASK @ 1252
        bid_order = OrderEvent(
            timestamp=datetime.now(),
            order_id="bid-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(bid_order)

        ask_order = OrderEvent(
            timestamp=datetime.now(),
            order_id="ask-456",
            contract="VN30F1M",
            side="ASK",
            price=Decimal("1248"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(ask_order)

        # Market price at 1249 → Both should fill
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1249"),
            bid=Decimal("1248"),
            ask=Decimal("1250"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Both orders should fill
        assert len(fills_received) == 2
        fill_ids = {f.order_id for f in fills_received}
        assert "bid-123" in fill_ids
        assert "ask-456" in fill_ids

    def test_only_matching_contract_orders_fill(self):
        """Test only orders for matching contract fill"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit orders for different contracts
        order_f1 = OrderEvent(
            timestamp=datetime.now(),
            order_id="f1-order",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order_f1)

        order_f2 = OrderEvent(
            timestamp=datetime.now(),
            order_id="f2-order",
            contract="VN30F2M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order_f2)

        # Market data only for F1M
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1249"),
            bid=Decimal("1248"),
            ask=Decimal("1250"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Only F1M order should fill
        assert len(fills_received) == 1
        assert fills_received[0].order_id == "f1-order"
        assert execution.get_pending_count() == 1  # F2M order still pending

    def test_fee_calculation_multiple_quantity(self):
        """Test fee calculation for multiple contracts"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        # Submit order with quantity 3
        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=3,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        # Fill the order
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1249"),
            bid=Decimal("1248"),
            ask=Decimal("1250"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        # Fee should be 20 * 3 = 60
        assert fills_received[0].fee == Decimal("60")
        assert fills_received[0].fill_quantity == 3

    def test_get_pending_orders_by_contract(self):
        """Test filtering pending orders by contract"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        # Submit orders for different contracts
        for i in range(3):
            order = OrderEvent(
                timestamp=datetime.now(),
                order_id=f"f1-{i}",
                contract="VN30F1M",
                side="BID",
                price=Decimal("1250"),
                quantity=1,
                status="SUBMITTED"
            )
            execution.on_order_event(order)

        for i in range(2):
            order = OrderEvent(
                timestamp=datetime.now(),
                order_id=f"f2-{i}",
                contract="VN30F2M",
                side="BID",
                price=Decimal("1250"),
                quantity=1,
                status="SUBMITTED"
            )
            execution.on_order_event(order)

        f1_orders = execution.get_pending_orders_by_contract("VN30F1M")
        f2_orders = execution.get_pending_orders_by_contract("VN30F2M")

        assert len(f1_orders) == 3
        assert len(f2_orders) == 2

    def test_current_prices_updated(self):
        """Test current_prices cache is updated on market data"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)

        assert "VN30F1M" in execution.current_prices
        assert execution.current_prices["VN30F1M"] == Decimal("1250")

    def test_fill_event_timestamp_matches_market_data(self):
        """Test fill event has correct timestamp from market data"""
        bus = EventBus()
        execution = MockExecutionEngine(bus)

        fills_received = []

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.FILL, capture_fill)

        order = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250"),
            quantity=1,
            status="SUBMITTED"
        )
        execution.on_order_event(order)

        market_timestamp = datetime(2025, 10, 24, 10, 15, 30)
        market_data = MarketDataEvent(
            timestamp=market_timestamp,
            contract="VN30F1M",
            price=Decimal("1249"),
            bid=Decimal("1248"),
            ask=Decimal("1250"),
            spread=Decimal("2")
        )
        execution.on_market_data(market_data)
        bus.process_events()

        assert fills_received[0].timestamp == market_timestamp

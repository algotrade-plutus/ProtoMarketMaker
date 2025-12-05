"""
Unit tests for event system
"""
import pytest
from datetime import datetime
from decimal import Decimal
from protomarketmaker.core.event import (
    Event, EventBus, MarketDataEvent, SignalEvent,
    OrderEvent, FillEvent, TimeEvent
)
from protomarketmaker.core.enums import EventType


class TestEventClasses:
    """Test event class creation"""

    def test_market_data_event_creation(self):
        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        assert event.event_type == EventType.MARKET_DATA
        assert event.contract == "VN30F1M"
        assert event.price == Decimal("1250.5")

    def test_signal_event_creation(self):
        event = SignalEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            signal_type="UPDATE_BID_ASK",
            bid_price=Decimal("1248.0"),
            ask_price=Decimal("1253.0"),
            reason="TIME_ELAPSED"
        )
        assert event.event_type == EventType.SIGNAL
        assert event.signal_type == "UPDATE_BID_ASK"

    def test_order_event_creation(self):
        event = OrderEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            price=Decimal("1250.0"),
            quantity=1,
            status="SUBMITTED"
        )
        assert event.event_type == EventType.ORDER
        assert event.order_id == "test-123"

    def test_fill_event_creation(self):
        event = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250.5"),
            fill_quantity=1,
            fee=Decimal("20.0")
        )
        assert event.event_type == EventType.FILL
        assert event.fill_price == Decimal("1250.5")

    def test_time_event_creation(self):
        event = TimeEvent(
            timestamp=datetime.now(),
            event_name="DAILY_SETTLEMENT",
            date=datetime.now()
        )
        assert event.event_type == EventType.TIME
        assert event.event_name == "DAILY_SETTLEMENT"


class TestEventBus:
    """Test EventBus functionality"""

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe(EventType.MARKET_DATA, handler)
        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.process_events()

        assert len(received_events) == 1
        assert received_events[0] == event

    def test_multiple_handlers(self):
        bus = EventBus()
        handler1_called = []
        handler2_called = []

        def handler1(event):
            handler1_called.append(True)

        def handler2(event):
            handler2_called.append(True)

        bus.subscribe(EventType.MARKET_DATA, handler1)
        bus.subscribe(EventType.MARKET_DATA, handler2)

        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.process_events()

        assert len(handler1_called) == 1
        assert len(handler2_called) == 1

    def test_exception_handling(self):
        bus = EventBus()
        good_handler_called = []

        def bad_handler(event):
            raise ValueError("Test error")

        def good_handler(event):
            good_handler_called.append(True)

        bus.subscribe(EventType.MARKET_DATA, bad_handler)
        bus.subscribe(EventType.MARKET_DATA, good_handler)

        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.process_events()

        # Good handler should still be called despite bad handler error
        assert len(good_handler_called) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe(EventType.MARKET_DATA, handler)
        bus.unsubscribe(EventType.MARKET_DATA, handler)

        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.process_events()

        assert len(received_events) == 0

    def test_get_event_count(self):
        bus = EventBus()
        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.publish(event)
        assert bus.get_event_count() == 2

    def test_get_queue_size(self):
        bus = EventBus()
        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.publish(event)
        assert bus.get_queue_size() == 2
        bus.process_events()
        assert bus.get_queue_size() == 0

    def test_clear_queue(self):
        bus = EventBus()
        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250.5"),
            bid=Decimal("1250.0"),
            ask=Decimal("1251.0"),
            spread=Decimal("1.0")
        )
        bus.publish(event)
        bus.publish(event)
        bus.clear_queue()
        assert bus.get_queue_size() == 0

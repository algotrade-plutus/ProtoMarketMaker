"""
Unit tests for OMS
"""
import pytest
from decimal import Decimal
from datetime import datetime
from protomarketmaker.core.event import EventBus, SignalEvent, FillEvent
from protomarketmaker.core.enums import OrderSide, OrderStatus
from protomarketmaker.engine.oms import OrderManager


class TestOrderManager:
    """Test OMS functionality"""

    def test_create_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order(
            "VN30F1M",
            OrderSide.BID,
            Decimal("1250"),
            1
        )

        assert order.contract == "VN30F1M"
        assert order.side == OrderSide.BID
        assert order.status == OrderStatus.CREATED
        assert order.order_id in oms.orders

    def test_submit_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order(
            "VN30F1M",
            OrderSide.BID,
            Decimal("1250"),
            1
        )

        success = oms.submit_order(order)

        assert success is True
        assert order.status == OrderStatus.SUBMITTED
        assert order.order_id in oms.active_orders
        assert order.submitted_at is not None

    def test_cancel_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order(
            "VN30F1M",
            OrderSide.BID,
            Decimal("1250"),
            1
        )
        oms.submit_order(order)

        success = oms.cancel_order(order.order_id)

        assert success is True
        assert order.status == OrderStatus.CANCELLED
        assert order.order_id not in oms.active_orders
        assert order.cancelled_at is not None

    def test_cancel_nonexistent_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        success = oms.cancel_order("nonexistent-order-id")

        assert success is False

    def test_cancel_already_filled_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order(
            "VN30F1M",
            OrderSide.BID,
            Decimal("1250"),
            1
        )
        oms.submit_order(order)
        order.status = OrderStatus.FILLED

        success = oms.cancel_order(order.order_id)

        assert success is False

    def test_cancel_all_orders(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order1 = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        order2 = oms.create_order("VN30F1M", OrderSide.ASK, Decimal("1255"), 1)
        oms.submit_order(order1)
        oms.submit_order(order2)

        oms.cancel_all_orders()

        assert len(oms.active_orders) == 0
        assert order1.status == OrderStatus.CANCELLED
        assert order2.status == OrderStatus.CANCELLED

    def test_cancel_all_orders_for_contract(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order1 = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        order2 = oms.create_order("VN30F2M", OrderSide.BID, Decimal("1260"), 1)
        oms.submit_order(order1)
        oms.submit_order(order2)

        oms.cancel_all_orders(contract="VN30F1M")

        assert len(oms.active_orders) == 1
        assert order1.status == OrderStatus.CANCELLED
        assert order2.status == OrderStatus.SUBMITTED

    def test_get_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)

        retrieved_order = oms.get_order(order.order_id)

        assert retrieved_order is order

    def test_get_order_nonexistent(self):
        bus = EventBus()
        oms = OrderManager(bus)

        retrieved_order = oms.get_order("nonexistent-id")

        assert retrieved_order is None

    def test_get_active_orders(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order1 = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        order2 = oms.create_order("VN30F1M", OrderSide.ASK, Decimal("1255"), 1)
        oms.submit_order(order1)
        oms.submit_order(order2)

        active_orders = oms.get_active_orders()

        assert len(active_orders) == 2
        assert order1 in active_orders
        assert order2 in active_orders

    def test_get_active_orders_by_contract(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order1 = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        order2 = oms.create_order("VN30F2M", OrderSide.BID, Decimal("1260"), 1)
        oms.submit_order(order1)
        oms.submit_order(order2)

        active_orders = oms.get_active_orders_by_contract("VN30F1M")

        assert len(active_orders) == 1
        assert active_orders[0] is order1

    def test_on_signal_event(self):
        bus = EventBus()
        oms = OrderManager(bus)

        signal = SignalEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            signal_type="UPDATE_BID_ASK",
            bid_price=Decimal("1248"),
            ask_price=Decimal("1253"),
            reason="TIME_ELAPSED"
        )

        oms.on_signal_event(signal)

        active_orders = oms.get_active_orders_by_contract("VN30F1M")
        assert len(active_orders) == 2  # Bid and Ask

        bid_orders = [o for o in active_orders if o.side == OrderSide.BID]
        ask_orders = [o for o in active_orders if o.side == OrderSide.ASK]

        assert len(bid_orders) == 1
        assert len(ask_orders) == 1
        assert bid_orders[0].price == Decimal("1248")
        assert ask_orders[0].price == Decimal("1253")

    def test_on_signal_event_cancels_old_orders(self):
        bus = EventBus()
        oms = OrderManager(bus)

        # First signal
        signal1 = SignalEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            signal_type="UPDATE_BID_ASK",
            bid_price=Decimal("1248"),
            ask_price=Decimal("1253"),
            reason="INITIAL"
        )
        oms.on_signal_event(signal1)

        # Second signal (should cancel old orders)
        signal2 = SignalEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            signal_type="UPDATE_BID_ASK",
            bid_price=Decimal("1250"),
            ask_price=Decimal("1255"),
            reason="TIME_ELAPSED"
        )
        oms.on_signal_event(signal2)

        active_orders = oms.get_active_orders_by_contract("VN30F1M")
        assert len(active_orders) == 2  # Only new orders

        # Check that old orders were cancelled
        cancelled_orders = [
            o for o in oms.orders.values()
            if o.status == OrderStatus.CANCELLED
        ]
        assert len(cancelled_orders) == 2

    def test_on_fill_event(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        oms.submit_order(order)

        fill = FillEvent(
            timestamp=datetime.now(),
            order_id=order.order_id,
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250.5"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        oms.on_fill_event(fill)

        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 1
        assert order.filled_price == Decimal("1250.5")
        assert order.order_id not in oms.active_orders
        assert order.filled_at is not None

    def test_on_fill_event_partial_fill(self):
        bus = EventBus()
        oms = OrderManager(bus)

        order = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 3)
        oms.submit_order(order)

        fill = FillEvent(
            timestamp=datetime.now(),
            order_id=order.order_id,
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250.5"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        oms.on_fill_event(fill)

        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 1
        assert order.order_id in oms.active_orders

    def test_on_fill_event_unknown_order(self):
        bus = EventBus()
        oms = OrderManager(bus)

        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="unknown-order-id",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250.5"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        # Should not crash, just log error
        oms.on_fill_event(fill)

    def test_get_statistics(self):
        bus = EventBus()
        oms = OrderManager(bus)

        # Create and submit orders
        order1 = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        order2 = oms.create_order("VN30F1M", OrderSide.ASK, Decimal("1255"), 1)
        order3 = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1249"), 1)

        oms.submit_order(order1)
        oms.submit_order(order2)
        oms.submit_order(order3)

        # Fill one order
        fill = FillEvent(
            timestamp=datetime.now(),
            order_id=order1.order_id,
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        oms.on_fill_event(fill)

        # Cancel one order
        oms.cancel_order(order2.order_id)

        stats = oms.get_statistics()

        assert stats['total_orders'] == 3
        assert stats['active_orders'] == 1
        assert stats['filled_orders'] == 1
        assert stats['cancelled_orders'] == 1
        assert stats['rejected_orders'] == 0

    def test_order_event_published_on_submit(self):
        bus = EventBus()
        oms = OrderManager(bus)

        published_events = []

        def capture_event(event):
            published_events.append(event)

        from core.enums import EventType
        bus.subscribe(EventType.ORDER, capture_event)

        order = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
        oms.submit_order(order)
        bus.process_events()

        # Event should have been published
        assert bus.get_event_count() > 0
        assert len(published_events) == 1
        assert published_events[0].order_id == order.order_id

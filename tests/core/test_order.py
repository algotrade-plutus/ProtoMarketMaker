"""
Unit tests for Order class
"""
import pytest
from decimal import Decimal
from core.order import Order
from core.enums import OrderSide, OrderStatus


class TestOrder:
    """Test Order functionality"""

    def test_order_creation(self):
        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250.5"),
            quantity=1
        )
        assert order.contract == "VN30F1M"
        assert order.side == OrderSide.BID
        assert order.price == Decimal("1250.5")
        assert order.quantity == 1
        assert order.status == OrderStatus.CREATED
        assert len(order.order_id) > 0  # UUID generated

    def test_order_id_uniqueness(self):
        order1 = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        order2 = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        assert order1.order_id != order2.order_id

    def test_is_active(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        order.status = OrderStatus.SUBMITTED
        assert order.is_active() is True

        order.status = OrderStatus.FILLED
        assert order.is_active() is False

    def test_is_terminal(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        order.status = OrderStatus.SUBMITTED
        assert order.is_terminal() is False

        order.status = OrderStatus.FILLED
        assert order.is_terminal() is True

    def test_can_cancel(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        order.status = OrderStatus.SUBMITTED
        assert order.can_cancel() is True

        order.status = OrderStatus.FILLED
        assert order.can_cancel() is False

    def test_get_unfilled_quantity(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"), quantity=5)
        order.filled_quantity = 2
        assert order.get_unfilled_quantity() == 3

    def test_is_filled(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        assert order.is_filled() is False

        order.status = OrderStatus.FILLED
        assert order.is_filled() is True

    def test_is_cancelled(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        assert order.is_cancelled() is False

        order.status = OrderStatus.CANCELLED
        assert order.is_cancelled() is True

    def test_is_rejected(self):
        order = Order(contract="VN30F1M", side=OrderSide.BID, price=Decimal("1250"))
        assert order.is_rejected() is False

        order.status = OrderStatus.REJECTED
        assert order.is_rejected() is True

    def test_order_ask_side(self):
        order = Order(
            contract="VN30F1M",
            side=OrderSide.ASK,
            price=Decimal("1255.0"),
            quantity=2
        )
        assert order.side == OrderSide.ASK
        assert order.quantity == 2

    def test_order_str_representation(self):
        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250.5"),
            quantity=1
        )
        str_repr = str(order)
        assert "VN30F1M" in str_repr
        assert "BID" in str_repr
        assert "1250.5" in str_repr

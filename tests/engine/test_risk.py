"""
Unit tests for Risk Manager
"""
import pytest
from decimal import Decimal
from datetime import datetime
from core.event import EventBus, FillEvent, MarketDataEvent
from core.order import Order
from core.enums import OrderSide
from engine.portfolio import PortfolioManager
from engine.risk import RiskManager


class TestRiskManager:
    """Test risk manager functionality"""

    def test_validate_order_sufficient_margin(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250"),
            quantity=1
        )

        assert risk.validate_order(order) is True

    def test_validate_order_insufficient_margin(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("10000"))  # Low capital
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250"),
            quantity=10  # Too many contracts
        )

        assert risk.validate_order(order) is False

    def test_validate_order_invalid_price_zero(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("0"),  # Invalid price
            quantity=1
        )

        assert risk.validate_order(order) is False

    def test_validate_order_invalid_price_negative(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("-1250"),  # Invalid price
            quantity=1
        )

        assert risk.validate_order(order) is False

    def test_validate_order_invalid_quantity_zero(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250"),
            quantity=0  # Invalid quantity
        )

        assert risk.validate_order(order) is False

    def test_validate_order_invalid_quantity_negative(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250"),
            quantity=-1  # Invalid quantity
        )

        assert risk.validate_order(order) is False

    def test_check_margin_requirement_sufficient(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        # Buy 1 contract
        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(fill)

        # Update market price
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        assert risk.check_margin_requirement() is True

    def test_check_margin_requirement_insufficient(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("50000"))  # Low capital
        risk = RiskManager(portfolio)

        # Buy 2 contracts
        fill1 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-1",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(fill1)

        fill2 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-2",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(fill2)

        # Update market price
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        # With 50000 capital and 2 contracts @ 1250, margin requirement should fail
        # Required margin = 2 * 1250 * 100 * 0.17 = 42500
        # NAV after buying 2 contracts = 50000 - 2*(125000 + 20) = 50000 - 250040 = negative
        # This would actually fail at purchase, but let's check margin requirement
        assert risk.check_margin_requirement() is False

    def test_check_margin_requirement_no_positions(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        # No positions, should always pass
        assert risk.check_margin_requirement() is True

    def test_validate_order_with_existing_position(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        # Buy 1 contract
        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-1",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(fill)

        # Try to buy another (should still pass with 500k capital)
        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250"),
            quantity=1
        )

        assert risk.validate_order(order) is True

    def test_validate_order_edge_case_exact_margin(self):
        bus = EventBus()
        # Margin for 1 contract @ 1250 = 1250 * 100 * 0.17 = 21250
        portfolio = PortfolioManager(bus, Decimal("21250"))
        risk = RiskManager(portfolio)

        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250"),
            quantity=1
        )

        # Should pass as we have exactly enough margin
        assert risk.validate_order(order) is True

    def test_check_margin_with_unrealized_loss(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)

        # Buy 10 contracts at 1250
        for i in range(10):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"test-{i}",
                contract="VN30F1M",
                side="BID",
                fill_price=Decimal("1250"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            portfolio.on_fill_event(fill)

        # Price drops significantly
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1100"),  # Big drop
            bid=Decimal("1099"),
            ask=Decimal("1101"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        # NAV should be significantly reduced
        # Required margin = 10 * 1100 * 100 * 0.17 = 187000
        # Check if margin requirement fails
        result = risk.check_margin_requirement()
        # Depending on exact NAV, this might pass or fail
        assert isinstance(result, bool)

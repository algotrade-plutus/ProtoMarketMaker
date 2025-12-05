"""
Unit tests for Portfolio Manager
"""
import pytest
from decimal import Decimal
from datetime import datetime
from protomarketmaker.core.event import EventBus, FillEvent, MarketDataEvent, TimeEvent
from protomarketmaker.engine.portfolio import PortfolioManager


class TestPortfolioManager:
    """Test portfolio functionality"""

    def test_initial_state(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        assert portfolio.cash == Decimal("500000")
        assert portfolio.calculate_nav() == Decimal("500000")
        assert len(portfolio.positions) == 0

    def test_get_position_creates_new(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        pos = portfolio.get_position("VN30F1M")

        assert pos.contract == "VN30F1M"
        assert pos.quantity == 0
        assert pos.is_flat()

    def test_on_fill_buy(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

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

        pos = portfolio.get_position("VN30F1M")
        assert pos.quantity == 1
        assert pos.average_price == Decimal("1250")
        # Cash doesn't change on fills (futures trading - updates at settlement)
        assert portfolio.cash == Decimal("500000")
        assert pos.total_fees == Decimal("20")

    def test_on_fill_sell(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # First buy
        buy_fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(buy_fill)

        # Then sell
        sell_fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-124",
            contract="VN30F1M",
            side="ASK",
            fill_price=Decimal("1260"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(sell_fill)

        pos = portfolio.get_position("VN30F1M")
        assert pos.quantity == 0
        # Realized PnL = (1260 - 1250) * 100 - fee = 1000 - 20 = 980
        assert pos.realized_pnl == Decimal("980")

    def test_on_fill_multiple_buys(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # First buy at 1250
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

        # Second buy at 1260
        fill2 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-2",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1260"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(fill2)

        pos = portfolio.get_position("VN30F1M")
        assert pos.quantity == 2
        # Average price = (1250 + 1260) / 2 = 1255
        assert pos.average_price == Decimal("1255")

    def test_on_market_data(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # Create position
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

        # Market data update
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1260"),
            bid=Decimal("1259"),
            ask=Decimal("1261"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        pos = portfolio.get_position("VN30F1M")
        # Unrealized PnL = (1260 - 1250) * 1 * 100 = 1000
        assert pos.unrealized_pnl == Decimal("1000")
        assert portfolio.current_prices["VN30F1M"] == Decimal("1260")

    def test_calculate_nav(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # Buy 1 contract at 1250
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

        # Price goes up to 1260
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1260"),
            bid=Decimal("1259"),
            ask=Decimal("1261"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        # NAV = cash + unrealized PnL
        # cash = 500000 (unchanged - futures don't deduct on fills)
        # unrealized = (1260 - 1250) * 100 = 1000
        # NAV = 500000 + 1000 = 501000
        nav = portfolio.calculate_nav()
        assert nav == Decimal("501000")

    def test_calculate_nav_with_loss(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # Buy 1 contract at 1250
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

        # Price goes down to 1240
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1240"),
            bid=Decimal("1239"),
            ask=Decimal("1241"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        # NAV = cash + unrealized PnL
        # cash = 500000 (unchanged - futures don't deduct on fills)
        # unrealized = (1240 - 1250) * 100 = -1000
        # NAV = 500000 - 1000 = 499000
        nav = portfolio.calculate_nav()
        assert nav == Decimal("499000")

    def test_get_available_margin(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        available = portfolio.get_available_margin("VN30F1M", Decimal("1250"))

        # NAV = 500000
        # Margin per contract = 1250 * 100 * 0.17 = 21250
        # Total placeable = 500000 / 21250 = 23.5 = 23 contracts
        assert available == 23

    def test_get_available_margin_with_existing_position(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

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

        available = portfolio.get_available_margin("VN30F1M", Decimal("1250"))

        # Uses initial_capital since no settlement yet (daily_nav is empty)
        # NAV = 500000
        # Margin per contract = 1250 * 100 * 0.17 = 21250
        # Total placeable = 500000 / 21250 = 23.5 = 23 contracts
        # But we already have 1 position, so available = 23 - 1 = 22
        assert available == 22

    def test_on_time_event_daily_settlement(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # Simulate day 1
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

        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1260"),
            bid=Decimal("1259"),
            ask=Decimal("1261"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        # Daily settlement
        time_event = TimeEvent(
            timestamp=datetime.now(),
            event_name="DAILY_SETTLEMENT",
            date=datetime.now()
        )
        portfolio.on_time_event(time_event)

        # Check daily returns were updated
        assert len(portfolio.daily_returns) == 1
        assert len(portfolio.daily_nav) == 2  # Initial + day 1
        assert len(portfolio.tracking_dates) == 1

    def test_get_summary(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

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
            price=Decimal("1260"),
            bid=Decimal("1259"),
            ask=Decimal("1261"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        summary = portfolio.get_summary()

        assert 'cash' in summary
        assert 'nav' in summary
        assert 'positions' in summary
        assert 'total_return' in summary
        assert 'VN30F1M' in summary['positions']

        # Verify position details
        pos_summary = summary['positions']['VN30F1M']
        assert pos_summary['quantity'] == 1
        assert pos_summary['average_price'] == 1250.0
        assert pos_summary['current_price'] == 1260.0
        assert pos_summary['market_value'] == 126000.0  # 1 * 1260 * 100
        assert 'unrealized_pnl' in pos_summary
        assert 'realized_pnl' in pos_summary
        assert 'total_fees' in pos_summary
        assert 'total_pnl' in pos_summary

    def test_short_position(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # Sell (short)
        sell_fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="ASK",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(sell_fill)

        pos = portfolio.get_position("VN30F1M")
        assert pos.quantity == -1
        assert pos.is_short()

        # Price goes down (profit for short)
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1240"),
            bid=Decimal("1239"),
            ask=Decimal("1241"),
            spread=Decimal("2")
        )
        portfolio.on_market_data(market_data)

        # Unrealized PnL = (1250 - 1240) * 1 * 100 = 1000
        assert pos.unrealized_pnl == Decimal("1000")

    def test_multiple_contracts(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("1000000"))

        # Buy VN30F1M
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

        # Buy VN30F2M
        fill2 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-2",
            contract="VN30F2M",
            side="BID",
            fill_price=Decimal("1260"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        portfolio.on_fill_event(fill2)

        assert len(portfolio.positions) == 2
        assert portfolio.get_position("VN30F1M").quantity == 1
        assert portfolio.get_position("VN30F2M").quantity == 1

    def test_get_performance_metrics_no_data(self):
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        metrics = portfolio.get_performance_metrics()

        # Should return error if no data
        assert 'error' in metrics

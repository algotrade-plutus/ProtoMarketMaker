"""
Integration tests for end-to-end event flow

Tests the complete flow:
Market Data → Strategy → OMS → Execution → Portfolio → Performance
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from core.event import EventBus, MarketDataEvent, TimeEvent
from core.enums import EventType
from engine.strategy import MarketMakerStrategy
from engine.oms import OrderManager
from engine.portfolio import PortfolioManager
from engine.risk import RiskManager
from engine.execution import MockExecutionEngine


class TestEndToEndFlow:
    """Test complete trading system integration"""

    def test_market_data_to_order_execution(self):
        """Test: Market data → Signal → Order → Fill → Portfolio update"""
        # Setup all components
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        # Track events
        signals_received = []
        orders_received = []
        fills_received = []

        def capture_signal(event):
            signals_received.append(event)

        def capture_order(event):
            orders_received.append(event)

        def capture_fill(event):
            fills_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)
        bus.subscribe(EventType.ORDER, capture_order)
        bus.subscribe(EventType.FILL, capture_fill)

        # Step 1: Send market data event
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()

        # Verify: Strategy generated signal
        assert len(signals_received) == 1
        assert signals_received[0].contract == "VN30F1M"
        assert signals_received[0].bid_price == Decimal("1247.1")
        assert signals_received[0].ask_price == Decimal("1252.9")

        # Step 2: Process signal (should create orders)
        bus.process_events()

        # Verify: OMS created and submitted 2 orders (bid + ask)
        submitted_orders = [o for o in orders_received if o.status == "SUBMITTED"]
        assert len(submitted_orders) == 2

        bid_order = [o for o in submitted_orders if o.side == "BID"][0]
        ask_order = [o for o in submitted_orders if o.side == "ASK"][0]

        assert bid_order.price == Decimal("1247.1")
        assert ask_order.price == Decimal("1252.9")

        # Step 3: Market price drops and hits bid
        market_data2 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1247.0"),  # Below bid price
            bid=Decimal("1246"),
            ask=Decimal("1248"),
            spread=Decimal("2")
        )
        bus.publish(market_data2)
        bus.process_events()

        # Verify: Bid order filled
        assert len(fills_received) == 1
        fill = fills_received[0]
        assert fill.order_id == bid_order.order_id
        assert fill.fill_price == Decimal("1247.0")
        assert fill.fee == Decimal("20")

        # Step 4: Process fill event
        bus.process_events()

        # Verify: Portfolio updated
        position = portfolio.get_position("VN30F1M")
        assert position.quantity == 1  # Long 1 contract
        assert position.average_price == Decimal("1247.0")

        # Cash doesn't change on fills (futures trading - updates at settlement)
        assert portfolio.cash == Decimal("500000")

        # Step 5: Verify strategy generated new signal after fill
        # (fill events trigger immediate signal generation)
        assert len(signals_received) >= 2

    def test_multiple_fills_with_inventory_changes(self):
        """Test inventory affects bid/ask prices"""
        # Setup
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # Send initial market data at price 1250
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()

        # Get initial signal (zero inventory, price=1250)
        initial_signal = signals_received[0]
        assert initial_signal.bid_price == Decimal("1247.1")
        assert initial_signal.ask_price == Decimal("1252.9")

        # Process signal to create orders
        bus.process_events()

        # Fill bid order (buy 1 contract) - price drops to fill the bid
        market_data2 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1247.1"),  # At bid price - fills the bid order
            bid=Decimal("1246"),
            ask=Decimal("1248"),
            spread=Decimal("2")
        )
        bus.publish(market_data2)
        bus.process_events()

        # Process fill and new signal
        bus.process_events()

        # Verify: Position updated
        position = portfolio.get_position("VN30F1M")
        assert position.quantity == 1  # Bought 1 contract

        # Get signal after fill (inventory = 1, price at 1247.1)
        post_fill_signal = [s for s in signals_received if s.reason == "ORDER_FILLED"][0]

        # With inventory = 1 and current price = 1247.1:
        # bid = 1247.1 - 2.9 * (1 * 0.02 + 1) = 1247.1 - 2.9 * 1.02 = 1247.1 - 2.958 = 1244.1
        # ask = 1247.1 - 2.9 * (0 * 0.02 - 1) = 1247.1 + 2.9 = 1250.0
        assert post_fill_signal.bid_price == Decimal("1244.1")
        assert post_fill_signal.ask_price == Decimal("1250.0")

    def test_risk_manager_blocks_invalid_order(self):
        """Test risk manager prevents orders with insufficient margin"""
        # Setup with low capital
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("10000"))  # Low capital
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        orders_received = []

        def capture_order(event):
            orders_received.append(event)

        bus.subscribe(EventType.ORDER, capture_order)

        # Send market data (high price)
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("5000"),  # High price
            bid=Decimal("4999"),
            ask=Decimal("5001"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()

        # Process signal
        bus.process_events()

        # Verify: Some orders may be rejected by risk manager
        # (With capital=10000 and price=5000, margin per contract = 5000*100*0.17 = 85000)
        # This should fail risk checks
        submitted_orders = [o for o in orders_received if o.status == "SUBMITTED"]

        # Should have 0 submitted orders (risk blocked them)
        assert len(submitted_orders) == 0

    def test_daily_settlement_flow(self):
        """Test daily settlement updates performance metrics"""
        # Setup
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        # Execute a trade
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()
        bus.process_events()  # Process signal

        # Fill bid order
        market_data2 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1247.0"),
            bid=Decimal("1246"),
            ask=Decimal("1248"),
            spread=Decimal("2")
        )
        bus.publish(market_data2)
        bus.process_events()
        bus.process_events()  # Process fill

        # Update unrealized PnL with new market price
        market_data3 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1260"),  # Price went up
            bid=Decimal("1259"),
            ask=Decimal("1261"),
            spread=Decimal("2")
        )
        bus.publish(market_data3)
        bus.process_events()

        # Send daily settlement event
        time_event = TimeEvent(
            timestamp=datetime.now(),
            event_name="DAILY_SETTLEMENT",
            date=datetime.now()
        )
        bus.publish(time_event)
        bus.process_events()

        # Verify: Daily return recorded
        assert len(portfolio.daily_returns) > 0
        assert len(portfolio.daily_nav) > 1

    def test_time_based_signal_generation(self):
        """Test strategy generates signals every 15 seconds"""
        # Setup
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # Initial market data at t=0
        start_time = datetime.now()
        market_data = MarketDataEvent(
            timestamp=start_time,
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()

        # Should generate initial signal (returns TIME_ELAPSED even for first call)
        assert len(signals_received) == 1
        assert signals_received[0].reason == "TIME_ELAPSED"

        # Market data at t=10s (before 15s interval)
        market_data2 = MarketDataEvent(
            timestamp=start_time + timedelta(seconds=10),
            contract="VN30F1M",
            price=Decimal("1251"),
            bid=Decimal("1250"),
            ask=Decimal("1252"),
            spread=Decimal("2")
        )
        bus.publish(market_data2)
        bus.process_events()

        # Should NOT generate new signal
        assert len(signals_received) == 1

        # Market data at t=16s (after 15s interval)
        market_data3 = MarketDataEvent(
            timestamp=start_time + timedelta(seconds=16),
            contract="VN30F1M",
            price=Decimal("1252"),
            bid=Decimal("1251"),
            ask=Decimal("1253"),
            spread=Decimal("2")
        )
        bus.publish(market_data3)
        bus.process_events()

        # Should generate time-based signal
        assert len(signals_received) == 2
        assert signals_received[1].reason == "TIME_ELAPSED"

    def test_full_round_trip_buy_and_sell(self):
        """Test complete round trip: buy → sell → PnL realization"""
        # Setup
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        # Initial market data
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()
        bus.process_events()  # Process signal

        # Fill bid order (buy at 1247.0)
        market_data2 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1247.0"),
            bid=Decimal("1246"),
            ask=Decimal("1248"),
            spread=Decimal("2")
        )
        bus.publish(market_data2)
        bus.process_events()
        bus.process_events()  # Process fill and new signal

        # Verify: Long 1 contract
        position = portfolio.get_position("VN30F1M")
        assert position.quantity == 1

        # Fill ask order (sell at 1253.0)
        market_data3 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1253.0"),  # Above ask price
            bid=Decimal("1252"),
            ask=Decimal("1254"),
            spread=Decimal("2")
        )
        bus.publish(market_data3)
        bus.process_events()
        bus.process_events()  # Process fill

        # Verify: Flat position
        position = portfolio.get_position("VN30F1M")
        assert position.quantity == 0

        # Verify: Realized PnL
        # Bought at 1247.0, sold at 1253.0
        # PnL = (1253.0 - 1247.0) * 100 - fee = 600 - 20 = 580
        assert position.realized_pnl == Decimal("580")

    def test_oms_statistics(self):
        """Test OMS statistics tracking"""
        # Setup
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        risk = RiskManager(portfolio)
        oms = OrderManager(bus, risk)
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))
        execution = MockExecutionEngine(bus)

        # Generate market data and fill orders
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        bus.publish(market_data)
        bus.process_events()
        bus.process_events()

        # Fill bid order
        market_data2 = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1247.0"),
            bid=Decimal("1246"),
            ask=Decimal("1248"),
            spread=Decimal("2")
        )
        bus.publish(market_data2)
        bus.process_events()

        # Get statistics
        stats = oms.get_statistics()

        assert stats['total_orders'] >= 2  # At least bid and ask
        assert stats['filled_orders'] >= 1  # At least one fill
        assert stats['active_orders'] >= 0  # May still have ask pending

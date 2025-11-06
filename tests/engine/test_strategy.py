"""
Unit tests for Strategy Engine
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from core.event import EventBus, MarketDataEvent, FillEvent, SignalEvent
from core.enums import EventType
from engine.portfolio import PortfolioManager
from engine.strategy import MarketMakerStrategy


class TestMarketMakerStrategy:
    """Test strategy functionality"""

    def test_initialization(self):
        """Test strategy initialization"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(
            bus, portfolio, Decimal("2.9"), update_interval_seconds=15
        )

        assert strategy.step == Decimal("2.9")
        assert strategy.update_interval == timedelta(seconds=15)
        assert strategy.last_update_time is None
        assert strategy.current_price is None

    def test_calculate_bid_ask_zero_inventory(self):
        """Test bid/ask calculation with zero inventory"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        bid, ask = strategy.calculate_bid_ask(Decimal("1250"), 0)

        # bid = 1250 - 2.9 * (0 * 0.02 + 1) = 1250 - 2.9 = 1247.1
        # ask = 1250 - 2.9 * (0 * 0.02 - 1) = 1250 + 2.9 = 1252.9
        assert bid == Decimal("1247.1")
        assert ask == Decimal("1252.9")

    def test_calculate_bid_ask_positive_inventory(self):
        """Test bid/ask calculation with positive inventory (long position)"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Positive inventory = long position, want to sell
        # Bid should decrease, ask stays same
        bid, ask = strategy.calculate_bid_ask(Decimal("1250"), 2)

        # bid = 1250 - 2.9 * (2 * 0.02 + 1) = 1250 - 2.9 * 1.04 = 1250 - 3.016 = 1247.0 (rounded)
        # ask = 1250 - 2.9 * (0 * 0.02 - 1) = 1250 + 2.9 = 1252.9
        assert bid == Decimal("1247.0")  # Lower than zero inventory
        assert ask == Decimal("1252.9")

    def test_calculate_bid_ask_negative_inventory(self):
        """Test bid/ask calculation with negative inventory (short position)"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Negative inventory = short position, want to buy
        # Bid stays same, ask increases
        bid, ask = strategy.calculate_bid_ask(Decimal("1250"), -2)

        # bid = 1250 - 2.9 * (0 * 0.02 + 1) = 1250 - 2.9 = 1247.1
        # ask = 1250 - 2.9 * (-2 * 0.02 - 1) = 1250 - 2.9 * (-1.04) = 1250 + 3.016 = 1253.0 (rounded)
        assert bid == Decimal("1247.1")
        assert ask == Decimal("1253.0")  # Higher than zero inventory

    def test_calculate_bid_ask_large_positive_inventory(self):
        """Test bid/ask with large positive inventory"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        bid, ask = strategy.calculate_bid_ask(Decimal("1250"), 5)

        # bid = 1250 - 2.9 * (5 * 0.02 + 1) = 1250 - 2.9 * 1.1 = 1250 - 3.19 = 1246.8 (rounded)
        assert bid == Decimal("1246.8")
        assert ask == Decimal("1252.9")

    def test_calculate_bid_ask_large_negative_inventory(self):
        """Test bid/ask with large negative inventory"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        bid, ask = strategy.calculate_bid_ask(Decimal("1250"), -5)

        # ask = 1250 - 2.9 * (-5 * 0.02 - 1) = 1250 - 2.9 * (-1.1) = 1250 + 3.19 = 1253.2 (rounded)
        assert bid == Decimal("1247.1")
        assert ask == Decimal("1253.2")

    def test_should_update_orders_initial(self):
        """Test should_update_orders returns True on first call"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        should_update, reason = strategy.should_update_orders(datetime.now())

        assert should_update is True
        # Returns "TIME_ELAPSED" even for first call (matches original backtest)
        assert reason == "TIME_ELAPSED"

    def test_should_update_orders_before_interval(self):
        """Test should_update_orders returns False before interval elapsed"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Set last update time
        start_time = datetime.now()
        strategy.last_update_time = start_time

        # Check 10 seconds later (before 15 second interval)
        should_update, reason = strategy.should_update_orders(
            start_time + timedelta(seconds=10)
        )

        assert should_update is False
        assert reason == ""

    def test_should_update_orders_after_interval(self):
        """Test should_update_orders returns True after interval elapsed"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Set last update time
        start_time = datetime.now()
        strategy.last_update_time = start_time

        # Check 16 seconds later (after 15 second interval)
        should_update, reason = strategy.should_update_orders(
            start_time + timedelta(seconds=16)
        )

        assert should_update is True
        assert reason == "TIME_ELAPSED"

    def test_should_update_orders_exactly_at_interval(self):
        """Test should_update_orders at exactly interval boundary"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        start_time = datetime.now()
        strategy.last_update_time = start_time

        # Check exactly 15 seconds later
        should_update, reason = strategy.should_update_orders(
            start_time + timedelta(seconds=15)
        )

        assert should_update is True
        assert reason == "TIME_ELAPSED"

    def test_on_market_data_updates_state(self):
        """Test on_market_data updates current price and contract"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        event = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )

        strategy.on_market_data(event)

        assert strategy.current_price == Decimal("1250")
        assert strategy.current_contract == "VN30F1M"

    def test_on_market_data_generates_initial_signal(self):
        """Test on_market_data generates signal on first call"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # Send market data event
        market_data = MarketDataEvent(
            timestamp=datetime.now(),
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )

        strategy.on_market_data(market_data)
        bus.process_events()

        # Should generate signal (returns TIME_ELAPSED even for first call)
        assert len(signals_received) == 1
        assert signals_received[0].reason == "TIME_ELAPSED"
        assert signals_received[0].contract == "VN30F1M"

    def test_on_market_data_no_signal_before_interval(self):
        """Test on_market_data doesn't generate signal before interval"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # First market data (generates initial signal)
        start_time = datetime.now()
        market_data1 = MarketDataEvent(
            timestamp=start_time,
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        strategy.on_market_data(market_data1)
        bus.process_events()

        # Second market data 10 seconds later (no signal)
        market_data2 = MarketDataEvent(
            timestamp=start_time + timedelta(seconds=10),
            contract="VN30F1M",
            price=Decimal("1251"),
            bid=Decimal("1250"),
            ask=Decimal("1252"),
            spread=Decimal("2")
        )
        strategy.on_market_data(market_data2)
        bus.process_events()

        # Should only have 1 signal (initial)
        assert len(signals_received) == 1

    def test_on_market_data_signal_after_interval(self):
        """Test on_market_data generates signal after interval"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # First market data
        start_time = datetime.now()
        market_data1 = MarketDataEvent(
            timestamp=start_time,
            contract="VN30F1M",
            price=Decimal("1250"),
            bid=Decimal("1249"),
            ask=Decimal("1251"),
            spread=Decimal("2")
        )
        strategy.on_market_data(market_data1)
        bus.process_events()

        # Second market data 16 seconds later (should generate signal)
        market_data2 = MarketDataEvent(
            timestamp=start_time + timedelta(seconds=16),
            contract="VN30F1M",
            price=Decimal("1251"),
            bid=Decimal("1250"),
            ask=Decimal("1252"),
            spread=Decimal("2")
        )
        strategy.on_market_data(market_data2)
        bus.process_events()

        # Should have 2 signals
        assert len(signals_received) == 2
        assert signals_received[1].reason == "TIME_ELAPSED"

    def test_on_fill_event_generates_signal(self):
        """Test on_fill_event generates signal immediately"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Set current price first
        strategy.current_price = Decimal("1250")
        strategy.current_contract = "VN30F1M"

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # Send fill event
        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        strategy.on_fill_event(fill)
        bus.process_events()

        # Should generate signal (order filled)
        assert len(signals_received) == 1
        assert signals_received[0].reason == "ORDER_FILLED"

    def test_on_fill_event_no_signal_without_price(self):
        """Test on_fill_event doesn't generate signal if no current price"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Don't set current price

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        # Send fill event
        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        strategy.on_fill_event(fill)
        bus.process_events()

        # Should NOT generate signal
        assert len(signals_received) == 0

    def test_generate_signal_creates_correct_event(self):
        """Test generate_signal creates SignalEvent with correct data"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        strategy.current_price = Decimal("1250")
        strategy.current_contract = "VN30F1M"

        signals_received = []

        def capture_signal(event):
            signals_received.append(event)

        bus.subscribe(EventType.SIGNAL, capture_signal)

        timestamp = datetime.now()
        strategy.generate_signal(timestamp, "TEST")
        bus.process_events()

        signal = signals_received[0]
        assert signal.contract == "VN30F1M"
        assert signal.signal_type == "UPDATE_BID_ASK"
        assert signal.bid_price == Decimal("1247.1")
        assert signal.ask_price == Decimal("1252.9")
        assert signal.reason == "TEST"
        assert signal.timestamp == timestamp

    def test_generate_signal_updates_last_update_time(self):
        """Test generate_signal updates last_update_time"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        strategy.current_price = Decimal("1250")
        strategy.current_contract = "VN30F1M"

        timestamp = datetime.now()
        # Only TIME_ELAPSED reason updates last_update_time
        strategy.generate_signal(timestamp, "TIME_ELAPSED")

        assert strategy.last_update_time == timestamp

    def test_reset_clears_state(self):
        """Test reset clears strategy state"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(bus, portfolio, Decimal("2.9"))

        # Set some state
        strategy.last_update_time = datetime.now()
        strategy.current_price = Decimal("1250")

        # Reset
        strategy.reset()

        assert strategy.last_update_time is None
        assert strategy.current_price is None

    def test_different_step_values(self):
        """Test strategy with different step values"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))

        # Test with step = 1.0
        strategy1 = MarketMakerStrategy(bus, portfolio, Decimal("1.0"))
        bid1, ask1 = strategy1.calculate_bid_ask(Decimal("1250"), 0)
        assert bid1 == Decimal("1249.0")
        assert ask1 == Decimal("1251.0")

        # Test with step = 5.0
        strategy2 = MarketMakerStrategy(bus, portfolio, Decimal("5.0"))
        bid2, ask2 = strategy2.calculate_bid_ask(Decimal("1250"), 0)
        assert bid2 == Decimal("1245.0")
        assert ask2 == Decimal("1255.0")

    def test_custom_update_interval(self):
        """Test strategy with custom update interval"""
        bus = EventBus()
        portfolio = PortfolioManager(bus, Decimal("500000"))
        strategy = MarketMakerStrategy(
            bus, portfolio, Decimal("2.9"), update_interval_seconds=30
        )

        assert strategy.update_interval == timedelta(seconds=30)

        start_time = datetime.now()
        strategy.last_update_time = start_time

        # After 20 seconds: should not update
        should_update, _ = strategy.should_update_orders(
            start_time + timedelta(seconds=20)
        )
        assert should_update is False

        # After 31 seconds: should update
        should_update, reason = strategy.should_update_orders(
            start_time + timedelta(seconds=31)
        )
        assert should_update is True
        assert reason == "TIME_ELAPSED"

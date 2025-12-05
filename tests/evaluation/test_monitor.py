"""
Unit tests for Performance Monitor
"""
import pytest
from decimal import Decimal
from datetime import datetime

from protomarketmaker.core.event import EventBus, FillEvent, TimeEvent
from protomarketmaker.core.enums import EventType
from protomarketmaker.evaluation.monitor import PerformanceMonitor


class TestPerformanceMonitor:
    """Test performance monitor"""

    def test_initialization(self):
        """Test monitor initialization"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        assert monitor.total_trades == 0
        assert monitor.buy_count == 0
        assert monitor.sell_count == 0
        assert monitor.total_fees == Decimal('0')

    def test_track_buy_trade(self):
        """Test tracking a buy trade"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-123",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        monitor.on_fill_event(fill)

        assert monitor.total_trades == 1
        assert monitor.buy_count == 1
        assert monitor.sell_count == 0
        assert monitor.total_fees == Decimal("20")

    def test_track_sell_trade(self):
        """Test tracking a sell trade"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        fill = FillEvent(
            timestamp=datetime.now(),
            order_id="test-456",
            contract="VN30F1M",
            side="ASK",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )

        monitor.on_fill_event(fill)

        assert monitor.total_trades == 1
        assert monitor.buy_count == 0
        assert monitor.sell_count == 1

    def test_track_multiple_trades(self):
        """Test tracking multiple trades"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        # 3 buys, 2 sells
        for i in range(3):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"buy-{i}",
                contract="VN30F1M",
                side="BID",
                fill_price=Decimal("1250"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        for i in range(2):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"sell-{i}",
                contract="VN30F1M",
                side="ASK",
                fill_price=Decimal("1252"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        assert monitor.total_trades == 5
        assert monitor.buy_count == 3
        assert monitor.sell_count == 2
        assert monitor.total_fees == Decimal("100")

    def test_fees_by_contract(self):
        """Test fee tracking by contract"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        # Trades on different contracts
        fill1 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-1",
            contract="VN30F1M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        monitor.on_fill_event(fill1)

        fill2 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-2",
            contract="VN30F2M",
            side="BID",
            fill_price=Decimal("1250"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        monitor.on_fill_event(fill2)

        fill3 = FillEvent(
            timestamp=datetime.now(),
            order_id="test-3",
            contract="VN30F1M",
            side="ASK",
            fill_price=Decimal("1252"),
            fill_quantity=1,
            fee=Decimal("20")
        )
        monitor.on_fill_event(fill3)

        assert monitor.fees_by_contract["VN30F1M"] == Decimal("40")
        assert monitor.fees_by_contract["VN30F2M"] == Decimal("20")

    def test_get_current_metrics(self):
        """Test getting current metrics"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        # Add some trades
        for i in range(5):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"test-{i}",
                contract="VN30F1M",
                side="BID",
                fill_price=Decimal("1250"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        metrics = monitor.get_current_metrics()

        assert metrics['total_trades'] == 5
        assert metrics['buy_count'] == 5
        assert metrics['sell_count'] == 0
        assert metrics['total_fees'] == 100.0
        assert metrics['average_fee'] == 20.0

    def test_get_trade_history(self):
        """Test getting trade history"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        # Add 10 trades
        for i in range(10):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"test-{i}",
                contract="VN30F1M",
                side="BID",
                fill_price=Decimal(str(1250 + i)),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        # Get all trades
        all_trades = monitor.get_trade_history()
        assert len(all_trades) == 10

        # Get last 3 trades
        recent_trades = monitor.get_trade_history(limit=3)
        assert len(recent_trades) == 3
        assert recent_trades[-1]['price'] == Decimal("1259")

    def test_get_trades_by_contract(self):
        """Test getting trades for specific contract"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        # Add trades for different contracts
        for i in range(3):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"f1-{i}",
                contract="VN30F1M",
                side="BID",
                fill_price=Decimal("1250"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        for i in range(2):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"f2-{i}",
                contract="VN30F2M",
                side="BID",
                fill_price=Decimal("1250"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        f1_trades = monitor.get_trades_by_contract("VN30F1M")
        f2_trades = monitor.get_trades_by_contract("VN30F2M")

        assert len(f1_trades) == 3
        assert len(f2_trades) == 2

    def test_reset(self):
        """Test resetting monitor"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        # Add some trades
        for i in range(5):
            fill = FillEvent(
                timestamp=datetime.now(),
                order_id=f"test-{i}",
                contract="VN30F1M",
                side="BID",
                fill_price=Decimal("1250"),
                fill_quantity=1,
                fee=Decimal("20")
            )
            monitor.on_fill_event(fill)

        # Reset
        monitor.reset()

        assert monitor.total_trades == 0
        assert monitor.buy_count == 0
        assert monitor.sell_count == 0
        assert monitor.total_fees == Decimal('0')
        assert len(monitor.trades) == 0

    def test_time_event_handling(self):
        """Test handling time events"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        time_event = TimeEvent(
            timestamp=datetime.now(),
            event_name="DAILY_SETTLEMENT",
            date=datetime.now()
        )

        # Should not raise exception
        monitor.on_time_event(time_event)

    def test_metrics_with_no_trades(self):
        """Test metrics when no trades have been executed"""
        bus = EventBus()
        monitor = PerformanceMonitor(bus)

        metrics = monitor.get_current_metrics()

        assert metrics['total_trades'] == 0
        assert metrics['average_fee'] == 0
        assert metrics['total_fees'] == 0.0

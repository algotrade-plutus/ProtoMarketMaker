"""
End-to-end tests for Live Mode

Tests complete live mode workflows including:
- Connection with actual contract codes
- Contract resolution and auto-detection
- F2M subscription during rollover
- Manual mapping override
"""

import pytest
import time
import threading
from decimal import Decimal
from datetime import datetime, date
from unittest.mock import patch

from protomarketmaker.tools.redis_publisher import RedisMarketDataPublisher
from protomarketmaker.paper_trading.engine import RedisPaperTradingEngine
from protomarketmaker.utils.contract_resolver import ContractSymbolResolver
from protomarketmaker.core.event import EventBus, MarketDataEvent
from protomarketmaker.core.enums import EventType


pytestmark = pytest.mark.integration


@pytest.fixture(scope="function")
def redis_publisher():
    """Create and connect Redis publisher"""
    publisher = RedisMarketDataPublisher(
        redis_host='localhost',
        redis_port=6379,
        channel_prefix='market'
    )

    if not publisher.connect():
        pytest.skip("Redis not available")

    yield publisher

    # Cleanup
    publisher.disconnect()


@pytest.fixture(scope="function")
def live_engine():
    """Create live mode engine with actual contract codes"""
    engine = RedisPaperTradingEngine(
        initial_capital=Decimal('500000'),
        step=Decimal('2.9'),
        mode='live',
        redis_host='localhost',
        redis_port=6379,
        channel_prefix='market',
        contracts=['VN30F2510']  # October 2025 contract
    )

    yield engine

    # Cleanup
    if engine._running:
        engine.stop()


class TestLiveModeEndToEnd:
    """End-to-end tests for live mode workflows"""

    def test_live_mode_basic_connection(self, redis_publisher):
        """Test live mode connects with actual contract codes"""
        # Create publisher with actual contract code channel
        message_count = 0

        def publish_messages():
            nonlocal message_count
            for i in range(10):
                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': 'VN30F2510',
                    'price': 1250.0 + i,
                    'bid': 1249.0 + i,
                    'ask': 1251.0 + i,
                    'spread': 2.0,
                    'volume': 100
                }
                redis_publisher.publish_message('VN30F2510', message_data)
                message_count += 1
                time.sleep(0.1)

        # Create engine with actual contract code
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='live',
            contracts=['VN30F2510']
        )

        # Start publisher in background
        publisher_thread = threading.Thread(target=publish_messages, daemon=True)
        publisher_thread.start()

        time.sleep(0.2)

        # Run engine
        engine.start()
        time.sleep(2)

        # Process events
        for _ in range(3):
            engine.event_bus.process_events()
            time.sleep(0.1)

        results = engine.stop()
        publisher_thread.join(timeout=2)

        # Verify connection worked
        assert results is not None
        assert results.messages_received > 0

    def test_live_mode_auto_detection(self):
        """Test auto-detection resolves symbols to actual codes"""
        # Use ContractSymbolResolver to test auto-detection
        resolver = ContractSymbolResolver()

        # Test F1M resolution for current date
        f1m_code = resolver.resolve('VN30F1M')
        assert f1m_code.startswith('VN30F')
        assert len(f1m_code) == 9  # VN30F + YYMM = 9 chars

        # Test F2M resolution
        f2m_code = resolver.resolve('VN30F2M')
        assert f2m_code.startswith('VN30F')
        assert len(f2m_code) == 9

        # Verify F1M and F2M are different contracts
        assert f1m_code != f2m_code

        # Test engine can use resolved codes
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='live',
            contracts=[f1m_code]
        )

        assert engine.contracts == [f1m_code]

    def test_live_mode_f2m_subscription(self):
        """Test F2M subscription in live mode during rollover"""
        from data.redis_stream import RedisMarketDataHandler

        # Mock current date to be near expiration
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='live',
            f2m_window_days=3
        )

        # Test: If we're 2 days before expiration, F2M should be needed
        # Feb 15, 2022 is 2 days before Feb 17 expiration
        result = handler._should_subscribe_f2m(
            date(2022, 2, 15),
            'VN30F2202',
            'VN30F2202'  # Same contract (no code change yet)
        )

        assert result is True  # Should subscribe to F2M

    def test_live_mode_contract_rollover(self):
        """Test contract rollover detection in live mode"""
        from data.redis_stream import RedisMarketDataHandler

        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='live',
            f2m_window_days=3
        )

        # Test rollover detection when contract code changes
        # This simulates VN30F2201 expiring and moving to VN30F2202
        result = handler._detect_rollover_from_contract(
            'VN30F2202',  # New contract
            'VN30F2201'   # Previous contract
        )

        assert result is True  # Rollover detected

        # Test no rollover when contract stays same
        result = handler._detect_rollover_from_contract(
            'VN30F2202',
            'VN30F2202'
        )

        assert result is False  # No rollover

    def test_live_mode_with_manual_mappings(self):
        """Test live mode with manual contract mappings"""
        # Create resolver with manual mappings
        manual_mappings = {
            'VN30F1M': 'VN30F2510',
            'VN30F2M': 'VN30F2511'
        }

        resolver = ContractSymbolResolver(manual_mappings=manual_mappings)

        # Test manual mappings override auto-detection
        assert resolver.resolve('VN30F1M') == 'VN30F2510'
        assert resolver.resolve('VN30F2M') == 'VN30F2511'

        # Test engine can use manual mappings
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='live',
            contracts=['VN30F2510']  # Using manually mapped code
        )

        assert engine.contracts == ['VN30F2510']

    def test_live_mode_expiration_calculation(self):
        """Test expiration date calculation for live contracts"""
        resolver = ContractSymbolResolver()

        # Test October 2025 contract (VN30F2510)
        exp_date = resolver.get_expiration_date('VN30F2510')
        assert exp_date.year == 2025
        assert exp_date.month == 10
        assert exp_date.weekday() == 3  # Thursday

        # Verify it's the third Thursday
        # Count Thursdays in October 2025
        thursdays = []
        for day in range(1, 32):
            try:
                d = date(2025, 10, day)
                if d.weekday() == 3:  # Thursday
                    thursdays.append(d)
            except ValueError:
                break

        assert len(thursdays) >= 3
        assert exp_date == thursdays[2]  # Third Thursday

    def test_live_mode_days_to_expiration(self):
        """Test days to expiration calculation"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 13))

        # October 2025 third Thursday is Oct 16
        days = resolver.get_days_to_expiration('VN30F2510')

        # From Oct 13 to Oct 16 = 3 days
        assert days == 3

        # Test on expiration day
        resolver_exp_day = ContractSymbolResolver(reference_date=date(2025, 10, 16))
        assert resolver_exp_day.is_expiration_day('VN30F2510') is True

    def test_live_mode_resolution_summary(self):
        """Test resolution summary provides correct information"""
        resolver = ContractSymbolResolver()

        # Get summary for F1M and F2M
        summary = resolver.get_resolution_summary(['VN30F1M', 'VN30F2M'])

        assert 'VN30F1M' in summary
        assert 'VN30F2M' in summary

        # Verify F1M summary has required fields
        assert 'code' in summary['VN30F1M']
        assert 'expiration' in summary['VN30F1M']
        assert 'days_to_expiry' in summary['VN30F1M']

        # Verify F2M summary has required fields
        assert 'code' in summary['VN30F2M']
        assert 'expiration' in summary['VN30F2M']
        assert 'days_to_expiry' in summary['VN30F2M']

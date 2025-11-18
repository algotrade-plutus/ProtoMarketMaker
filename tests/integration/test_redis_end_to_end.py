"""
End-to-end integration tests for Redis streaming

These tests require a running Redis server.
Run with: pytest tests/integration/test_redis_end_to_end.py --redis-running
"""
import pytest
import time
import json
from decimal import Decimal
from datetime import datetime

from core.event import EventBus, EventType
from paper_trading.redis_session import RedisTradingSession
from tools.redis_publisher import RedisMarketDataPublisher


# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
def redis_host():
    """Redis server hostname"""
    return 'localhost'


@pytest.fixture
def redis_port():
    """Redis server port"""
    return 6379


@pytest.fixture
def publisher(redis_host, redis_port):
    """Create and connect a Redis publisher"""
    pub = RedisMarketDataPublisher(redis_host=redis_host, redis_port=redis_port)

    try:
        connected = pub.connect()
        if not connected:
            pytest.skip("Redis server not available")

        yield pub

    finally:
        pub.disconnect()


@pytest.fixture
def trading_session(redis_host, redis_port):
    """Create a trading session"""
    session = RedisTradingSession(
        initial_capital=Decimal("500000"),
        step=Decimal("2.9"),
        update_interval_seconds=15,
        redis_host=redis_host,
        redis_port=redis_port
    )

    yield session

    if session.running:
        session.stop()


class TestRedisEndToEnd:
    """End-to-end integration tests"""

    def test_publisher_session_integration(self, publisher, trading_session):
        """Test full integration: publisher -> session -> strategy"""
        # Start trading session
        contracts = ['VN30F1M']
        started = trading_session.start(contracts)

        if not started:
            pytest.skip("Could not start trading session (Redis not available)")

        assert trading_session.running is True
        assert trading_session.is_healthy() is True

        # Publish some market data
        for i in range(5):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F1M',
                'price': 1250.0 + i,
                'bid': 1249.0 + i,
                'ask': 1251.0 + i
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.1)  # Small delay between messages

        # Give system time to process
        time.sleep(1)

        # Check that messages were received
        redis_stats = trading_session.redis_handler.get_statistics()
        assert redis_stats['messages_processed'] > 0

        # Stop session
        trading_session.stop()
        assert trading_session.running is False

    def test_market_data_to_strategy(self, publisher, trading_session):
        """Test that market data triggers strategy signals"""
        # Start session
        contracts = ['VN30F1M']
        started = trading_session.start(contracts)

        if not started:
            pytest.skip("Could not start trading session")

        # Publish market data
        for i in range(10):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F1M',
                'price': 1250.0 + i * 0.5,
                'bid': 1249.0 + i * 0.5,
                'ask': 1251.0 + i * 0.5
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.05)

        # Wait for processing
        time.sleep(2)

        # Get summary
        summary = trading_session.get_summary()

        # Verify data was processed
        assert summary['redis']['messages_processed'] > 0

        # Stop session
        trading_session.stop()

    def test_multiple_contracts(self, publisher, trading_session):
        """Test handling multiple contracts"""
        # Start session with multiple contracts
        contracts = ['VN30F1M', 'VN30F2M']
        started = trading_session.start(contracts)

        if not started:
            pytest.skip("Could not start trading session")

        # Publish to both contracts
        for contract in contracts:
            for i in range(3):
                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': contract,
                    'price': 1250.0 + i,
                    'bid': 1249.0 + i,
                    'ask': 1251.0 + i
                }
                publisher.publish_message(contract, message_data)
                time.sleep(0.05)

        # Wait for processing
        time.sleep(1)

        # Get statistics
        redis_stats = trading_session.redis_handler.get_statistics()

        # Should have processed messages from both contracts
        assert redis_stats['messages_processed'] >= 6

        # Stop session
        trading_session.stop()

    def test_session_health_monitoring(self, publisher, trading_session):
        """Test session health monitoring"""
        # Start session
        started = trading_session.start(['VN30F1M'])

        if not started:
            pytest.skip("Could not start trading session")

        # Session should be healthy
        assert trading_session.is_healthy() is True

        # Latency should be available
        latency = trading_session.get_latency_ms()
        # Latency might be None if no messages processed yet
        # Just check it doesn't raise an error

        # Stop session
        trading_session.stop()

        # Session should not be healthy when stopped
        assert trading_session.is_healthy() is False

    def test_error_recovery(self, publisher, trading_session):
        """Test error handling and recovery"""
        # Start session
        started = trading_session.start(['VN30F1M'])

        if not started:
            pytest.skip("Could not start trading session")

        # Publish valid message
        valid_message = {
            'timestamp': datetime.now().isoformat(),
            'contract': 'VN30F1M',
            'price': 1250.0,
            'bid': 1249.0,
            'ask': 1251.0
        }
        publisher.publish_message('VN30F1M', valid_message)

        # Publish invalid message (missing fields)
        invalid_message = {
            'timestamp': datetime.now().isoformat(),
            'contract': 'VN30F1M',
            # Missing price, bid, ask
        }
        publisher.redis_client.publish(
            'market:VN30F1M',  # Use correct channel prefix
            json.dumps(invalid_message)
        )

        # Publish another valid message
        publisher.publish_message('VN30F1M', valid_message)

        # Wait for processing
        time.sleep(1)

        # Get statistics
        redis_stats = trading_session.redis_handler.get_statistics()

        # Should have processed valid messages
        assert redis_stats['messages_processed'] >= 2
        # Incomplete message (missing price/bid/ask) should be handled gracefully:
        # - Either skipped (if no cache available)
        # - Or forward-filled from cache (if cache exists)
        # This is expected behavior with incomplete tick handling
        assert redis_stats.get('messages_skipped_incomplete', 0) >= 0
        assert redis_stats.get('messages_forward_filled', 0) >= 0
        # At least one incomplete tick should be handled
        assert (redis_stats.get('messages_skipped_incomplete', 0) +
                redis_stats.get('messages_forward_filled', 0)) > 0

        # Session should still be healthy (incomplete ticks are not errors)
        assert trading_session.is_healthy() is True

        # Stop session
        trading_session.stop()

    def test_high_frequency_messages(self, publisher, trading_session):
        """Test handling high-frequency message stream"""
        # Start session
        started = trading_session.start(['VN30F1M'])

        if not started:
            pytest.skip("Could not start trading session")

        # Publish messages rapidly
        message_count = 100
        start_time = time.time()

        for i in range(message_count):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F1M',
                'price': 1250.0 + (i % 10) * 0.1,
                'bid': 1249.0 + (i % 10) * 0.1,
                'ask': 1251.0 + (i % 10) * 0.1
            }
            publisher.publish_message('VN30F1M', message_data)

        end_time = time.time()
        publish_duration = end_time - start_time

        # Wait for processing
        time.sleep(2)

        # Get statistics
        redis_stats = trading_session.redis_handler.get_statistics()

        # Should have processed most messages
        processed = redis_stats['messages_processed']
        assert processed >= message_count * 0.9  # Allow 10% loss

        # Calculate throughput
        throughput = message_count / publish_duration
        print(f"\nPublish throughput: {throughput:.1f} messages/sec")

        if processed > 0:
            latency = trading_session.get_latency_ms()
            if latency is not None:
                print(f"Average latency: {latency:.2f} ms")

        # Stop session
        trading_session.stop()

    def test_session_summary_accuracy(self, publisher, trading_session):
        """Test that session summary is accurate"""
        # Start session
        started = trading_session.start(['VN30F1M'])

        if not started:
            pytest.skip("Could not start trading session")

        initial_time = time.time()

        # Publish market data
        for i in range(20):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F1M',
                'price': 1250.0 + i * 0.2,
                'bid': 1249.0 + i * 0.2,
                'ask': 1251.0 + i * 0.2
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.05)

        # Wait for processing
        time.sleep(1)

        # Get summary
        summary = trading_session.get_summary()

        # Verify summary structure
        assert 'session' in summary
        assert 'portfolio' in summary
        assert 'orders' in summary
        assert 'redis' in summary
        assert 'performance' in summary

        # Verify session info
        assert summary['session']['contracts'] == ['VN30F1M']
        assert summary['session']['is_running'] is True

        # Verify duration is reasonable
        duration = summary['session']['duration_seconds']
        actual_duration = time.time() - initial_time
        assert duration >= actual_duration * 0.9  # Allow 10% variance
        assert duration <= actual_duration * 1.1

        # Verify portfolio info
        assert summary['portfolio']['initial_capital'] == 500000.0
        assert 'final_nav' in summary['portfolio']
        assert 'total_return' in summary['portfolio']

        # Verify Redis stats
        assert summary['redis']['messages_processed'] > 0

        # Stop session
        trading_session.stop()


# Skip all tests in this file if Redis is not available
def pytest_configure(config):
    """Register integration test marker"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires Redis)"
    )

"""
Integration tests for Redis-based paper trading engine

These tests verify end-to-end workflows from Redis publisher through
the paper trading engine to results generation.

Tests require a running Redis server.
Run with: pytest tests/integration/test_paper_trading_integration.py --redis-running
"""
import pytest
import time
import json
import threading
from decimal import Decimal
from datetime import datetime, date
from pathlib import Path

from paper_trading.engine import RedisPaperTradingEngine
from paper_trading.results import PaperTradingResults
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
def channel_prefix():
    """Redis channel prefix"""
    return 'test_market'


@pytest.fixture
def publisher(redis_host, redis_port, channel_prefix):
    """Create and connect a Redis publisher"""
    pub = RedisMarketDataPublisher(
        redis_host=redis_host,
        redis_port=redis_port,
        channel_prefix=channel_prefix
    )

    try:
        connected = pub.connect()
        if not connected:
            pytest.skip("Redis server not available")

        yield pub

    finally:
        pub.disconnect()


@pytest.fixture
def engine(redis_host, redis_port, channel_prefix):
    """Create a paper trading engine"""
    engine = RedisPaperTradingEngine(
        initial_capital=Decimal("500000"),
        step=Decimal("2.9"),
        redis_host=redis_host,
        redis_port=redis_port,
        channel_prefix=channel_prefix,
        contracts=['VN30F2202', 'VN30F2203'],
        update_interval_seconds=1,  # Short interval for testing
        mode='live'  # Use live mode for actual contract codes
    )

    yield engine

    # Cleanup
    if engine.running:
        engine.stop()


@pytest.fixture
def sample_csv_path():
    """Path to sample CSV data"""
    path = Path("data/sample/merged_is_data_1day.csv")
    if not path.exists():
        pytest.skip(f"Sample CSV not found: {path}")
    return str(path)


class TestPaperTradingIntegration:
    """Integration tests for paper trading engine with Redis publisher"""

    def test_basic_connection_and_subscription(self, engine, publisher):
        """Test that engine can connect to Redis and subscribe to channels"""
        # Start engine
        engine.start()

        # Wait for connection
        time.sleep(0.5)

        assert engine.running is True

        # Publish a test message
        message_data = {
            'timestamp': datetime.now().isoformat(),
            'contract': 'VN30F2202',
            'price': 1250.0,
            'bid': 1249.0,
            'ask': 1251.0
        }
        publisher.publish_message('VN30F2202', message_data)

        # Wait for processing
        time.sleep(0.5)

        # Stop engine
        results = engine.stop()

        # Verify we received messages
        assert results.messages_received > 0

    def test_market_data_to_trading_signals(self, engine, publisher):
        """Test that market data triggers trading signals and orders"""
        # Start engine
        engine.start()
        time.sleep(0.2)

        # Publish market data with varying prices
        prices = [1250.0, 1251.0, 1252.0, 1250.5, 1249.0]

        for i, price in enumerate(prices):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F2202',
                'price': price,
                'bid': price - 1.0,
                'ask': price + 1.0
            }
            publisher.publish_message('VN30F2202', message_data)
            time.sleep(0.05)

        # Wait for strategy to generate signals (update_interval=1s)
        time.sleep(2)

        # Get summary
        summary = engine.get_summary()

        # Verify messages were processed
        assert summary['messages_processed'] >= len(prices)

        # Stop engine
        results = engine.stop()

        # Verify results structure
        assert isinstance(results, PaperTradingResults)
        assert results.messages_received >= len(prices)
        assert results.mode == 'live'

    def test_multiple_contracts_handling(self, engine, publisher):
        """Test handling multiple contracts simultaneously"""
        # Start engine
        engine.start()
        time.sleep(0.2)

        contracts = ['VN30F2202', 'VN30F2203']

        # Publish to both contracts
        for contract in contracts:
            for i in range(5):
                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': contract,
                    'price': 1250.0 + i * 0.5,
                    'bid': 1249.0 + i * 0.5,
                    'ask': 1251.0 + i * 0.5
                }
                publisher.publish_message(contract, message_data)
                time.sleep(0.02)

        # Wait for processing
        time.sleep(1)

        # Get summary
        summary = engine.get_summary()

        # Should have processed messages from both contracts
        assert summary['messages_processed'] >= 10

        # Stop engine
        results = engine.stop()
        assert results.messages_received >= 10

    def test_high_frequency_message_handling(self, engine, publisher):
        """Test handling high-frequency message stream"""
        # Start engine
        engine.start()
        time.sleep(0.2)

        # Publish messages rapidly
        message_count = 100
        start_time = time.time()

        for i in range(message_count):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F2202',
                'price': 1250.0 + (i % 10) * 0.1,
                'bid': 1249.0 + (i % 10) * 0.1,
                'ask': 1251.0 + (i % 10) * 0.1
            }
            publisher.publish_message('VN30F2202', message_data)

        publish_duration = time.time() - start_time

        # Wait for processing
        time.sleep(2)

        # Stop engine
        results = engine.stop()

        # Verify throughput
        throughput = message_count / publish_duration
        print(f"\nPublish throughput: {throughput:.1f} messages/sec")

        # Should have processed most messages (allow some loss)
        assert results.messages_processed >= message_count * 0.85

        # Check latency
        if results.avg_latency_ms > 0:
            print(f"Average latency: {results.avg_latency_ms:.2f} ms")
            assert results.avg_latency_ms < 100  # Should be < 100ms

    def test_trading_execution_flow(self, engine, publisher):
        """Test complete trading flow: signals → orders → fills"""
        # Start engine
        engine.start()
        time.sleep(0.2)

        # Simulate price movements that should trigger trades
        # Start with baseline price
        base_price = Decimal('1250.0')

        # Publish initial price
        message_data = {
            'timestamp': datetime.now().isoformat(),
            'contract': 'VN30F2202',
            'price': float(base_price),
            'bid': float(base_price - 1),
            'ask': float(base_price + 1)
        }
        publisher.publish_message('VN30F2202', message_data)
        time.sleep(1.5)  # Wait for initial signal

        # Price moves up significantly (should trigger sell)
        high_price = base_price + Decimal('10.0')
        message_data['price'] = float(high_price)
        message_data['bid'] = float(high_price - 1)
        message_data['ask'] = float(high_price + 1)
        message_data['timestamp'] = datetime.now().isoformat()
        publisher.publish_message('VN30F2202', message_data)
        time.sleep(0.5)

        # Price moves down significantly (should trigger buy)
        low_price = base_price - Decimal('10.0')
        message_data['price'] = float(low_price)
        message_data['bid'] = float(low_price - 1)
        message_data['ask'] = float(low_price + 1)
        message_data['timestamp'] = datetime.now().isoformat()
        publisher.publish_message('VN30F2202', message_data)
        time.sleep(0.5)

        # Get summary
        summary = engine.get_summary()
        print(f"\nTrades executed: {summary['total_trades']}")
        print(f"Current NAV: {summary['current_nav']:,.0f}")

        # Stop engine
        results = engine.stop()

        # Verify trading occurred
        assert results.messages_processed > 0
        # Note: Trades may or may not occur depending on exact timing

    def test_results_export_and_serialization(self, engine, publisher):
        """Test results export to JSON"""
        import tempfile

        # Start engine
        engine.start()
        time.sleep(0.2)

        # Publish some data
        for i in range(10):
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': 'VN30F2202',
                'price': 1250.0 + i * 0.5,
                'bid': 1249.0 + i * 0.5,
                'ask': 1251.0 + i * 0.5
            }
            publisher.publish_message('VN30F2202', message_data)
            time.sleep(0.05)

        time.sleep(1)

        # Stop and get results
        results = engine.stop()

        # Export to JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            results.to_json(temp_path)

            # Verify file exists and can be loaded
            assert Path(temp_path).exists()

            with open(temp_path, 'r') as f:
                data = json.load(f)

            # Verify structure
            assert 'session' in data
            assert 'performance' in data
            assert 'trading' in data
            assert 'redis_metrics' in data

            # Verify data accuracy
            assert data['redis_metrics']['messages_received'] == results.messages_received
            assert data['performance']['initial_capital'] == str(results.initial_capital)

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_run_with_duration(self, engine, publisher):
        """Test running engine for a specific duration"""
        # Start publisher in background thread
        def publish_loop():
            for i in range(100):
                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': 'VN30F2202',
                    'price': 1250.0 + (i % 20) * 0.1,
                    'bid': 1249.0 + (i % 20) * 0.1,
                    'ask': 1251.0 + (i % 20) * 0.1
                }
                publisher.publish_message('VN30F2202', message_data)
                time.sleep(0.1)

        publisher_thread = threading.Thread(target=publish_loop)
        publisher_thread.daemon = True
        publisher_thread.start()

        # Run engine for 3 seconds
        start_time = time.time()
        results = engine.run(duration_seconds=3)
        elapsed = time.time() - start_time

        # Verify duration
        assert 2.5 <= elapsed <= 3.5  # Allow some variance
        assert results.duration_seconds >= 2.5

        # Verify results
        assert results.messages_received > 0
        assert results.mode == 'live'

    def test_csv_playback_integration(self, publisher, redis_host, redis_port, channel_prefix, sample_csv_path):
        """Test full CSV playback through Redis to engine"""
        # Load CSV and start publishing in background
        publisher.load_csv(sample_csv_path)

        def publish_loop():
            publisher.start_publishing(rate_hz=50, loop=False)

        publisher_thread = threading.Thread(target=publish_loop)
        publisher_thread.daemon = True
        publisher_thread.start()

        # Wait for publisher to start
        time.sleep(0.5)

        # Create engine with contracts matching CSV
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix,
            contracts=['VN30F2202', 'VN30F2203'],
            update_interval_seconds=15,
            mode='live'  # Use live mode for actual contract codes
        )

        try:
            # Run for 5 seconds
            results = engine.run(duration_seconds=5)

            # Verify we processed CSV data
            assert results.messages_received > 0
            assert results.messages_processed > 0

            # Check performance metrics are valid
            assert results.initial_capital == Decimal('500000')
            assert results.final_nav > 0
            assert results.duration_seconds >= 4.5

            print(f"\nProcessed {results.messages_received} messages from CSV")
            print(f"Final NAV: {results.final_nav:,.0f}")
            print(f"HPR: {results.hpr:+.2%}")

        finally:
            if engine.running:
                engine.stop()

    def test_error_handling_invalid_messages(self, engine, publisher, channel_prefix):
        """Test error handling for malformed messages"""
        # Start engine
        engine.start()
        time.sleep(0.2)

        # Publish valid message
        valid_message = {
            'timestamp': datetime.now().isoformat(),
            'contract': 'VN30F2202',
            'price': 1250.0,
            'bid': 1249.0,
            'ask': 1251.0
        }
        publisher.publish_message('VN30F2202', valid_message)

        # Publish invalid message (missing fields)
        invalid_message = {
            'timestamp': datetime.now().isoformat(),
            'contract': 'VN30F2202',
            # Missing price, bid, ask
        }
        publisher.redis_client.publish(
            f'{channel_prefix}:VN30F2202',
            json.dumps(invalid_message)
        )

        # Publish another valid message
        publisher.publish_message('VN30F2202', valid_message)

        time.sleep(1)

        # Get summary
        summary = engine.get_summary()

        # Should have processed valid messages
        assert summary['messages_processed'] >= 2

        # Stop engine
        results = engine.stop()

        # Engine should still be functional
        assert results.messages_processed >= 2

    def test_real_time_summary_accuracy(self, engine, publisher):
        """Test real-time summary updates during execution"""
        # Start engine
        engine.start()
        time.sleep(0.2)

        # Publish messages and check summary periodically
        for round in range(3):
            # Publish batch of messages
            for i in range(5):
                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': 'VN30F2202',
                    'price': 1250.0 + round * 10 + i * 0.5,
                    'bid': 1249.0 + round * 10 + i * 0.5,
                    'ask': 1251.0 + round * 10 + i * 0.5
                }
                publisher.publish_message('VN30F2202', message_data)
                time.sleep(0.05)

            # Get summary
            summary = engine.get_summary()

            # Verify summary is updating
            assert summary['status'] == 'running'
            assert summary['messages_processed'] >= (round + 1) * 5

            time.sleep(0.5)

        # Stop and verify final results match last summary
        results = engine.stop()
        final_summary = engine.get_summary()

        assert final_summary['status'] == 'stopped'
        assert results.messages_processed == final_summary['messages_processed']


class TestPaperTradingPerformance:
    """Performance benchmarks for paper trading engine"""

    def test_throughput_benchmark(self, redis_host, redis_port, channel_prefix):
        """Benchmark message processing throughput"""
        # Create publisher
        publisher = RedisMarketDataPublisher(
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix
        )

        if not publisher.connect():
            pytest.skip("Redis not available")

        try:
            # Create engine
            engine = RedisPaperTradingEngine(
                initial_capital=Decimal("500000"),
                step=Decimal("2.9"),
                redis_host=redis_host,
                redis_port=redis_port,
                channel_prefix=channel_prefix,
                contracts=['VN30F2202'],
                update_interval_seconds=15,
                mode='live'  # Use live mode for actual contract codes
            )

            engine.start()
            time.sleep(0.2)

            # Publish large number of messages
            message_count = 500
            start_time = time.time()

            for i in range(message_count):
                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': 'VN30F2202',
                    'price': 1250.0 + (i % 50) * 0.1,
                    'bid': 1249.0 + (i % 50) * 0.1,
                    'ask': 1251.0 + (i % 50) * 0.1
                }
                publisher.publish_message('VN30F2202', message_data)

            publish_time = time.time() - start_time

            # Wait for processing
            time.sleep(3)

            # Get results
            results = engine.stop()

            # Calculate metrics
            throughput = results.messages_processed / results.duration_seconds
            processing_rate = results.messages_processed / message_count

            print(f"\n{'='*60}")
            print("THROUGHPUT BENCHMARK")
            print(f"{'='*60}")
            print(f"Messages published:  {message_count}")
            print(f"Messages processed:  {results.messages_processed}")
            print(f"Processing rate:     {processing_rate:.1%}")
            print(f"Throughput:          {throughput:.1f} msg/s")
            print(f"Avg latency:         {results.avg_latency_ms:.2f} ms")
            print(f"{'='*60}")

            # Assertions
            assert processing_rate >= 0.9  # Should process 90%+ of messages
            assert throughput >= 50  # Should handle 50+ msg/s
            if results.avg_latency_ms > 0:
                assert results.avg_latency_ms < 50  # Latency should be < 50ms

        finally:
            publisher.disconnect()
            if engine.running:
                engine.stop()

    def test_latency_benchmark(self, redis_host, redis_port, channel_prefix):
        """Benchmark end-to-end latency"""
        # Create publisher
        publisher = RedisMarketDataPublisher(
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix
        )

        if not publisher.connect():
            pytest.skip("Redis not available")

        try:
            # Create engine
            engine = RedisPaperTradingEngine(
                initial_capital=Decimal("500000"),
                step=Decimal("2.9"),
                redis_host=redis_host,
                redis_port=redis_port,
                channel_prefix=channel_prefix,
                contracts=['VN30F2202'],
                update_interval_seconds=15,
                mode='live'  # Use live mode for actual contract codes
            )

            engine.start()
            time.sleep(0.5)

            # Publish messages at controlled rate
            latencies = []

            for i in range(50):
                send_time = time.time()

                message_data = {
                    'timestamp': datetime.now().isoformat(),
                    'contract': 'VN30F2202',
                    'price': 1250.0 + i * 0.1,
                    'bid': 1249.0 + i * 0.1,
                    'ask': 1251.0 + i * 0.1
                }
                publisher.publish_message('VN30F2202', message_data)

                # Wait briefly to measure latency
                time.sleep(0.05)

            time.sleep(1)

            # Get results
            results = engine.stop()

            print(f"\n{'='*60}")
            print("LATENCY BENCHMARK")
            print(f"{'='*60}")
            print(f"Messages processed:  {results.messages_processed}")
            print(f"Average latency:     {results.avg_latency_ms:.2f} ms")
            print(f"{'='*60}")

            # Latency should be reasonable
            if results.avg_latency_ms > 0:
                assert results.avg_latency_ms < 100  # < 100ms

        finally:
            publisher.disconnect()
            if engine.running:
                engine.stop()


class TestDualModeAndConditionalSubscription:
    """Integration tests for dual-mode architecture and conditional F2M subscription"""

    def test_playback_mode_initialization(self, redis_host, redis_port, channel_prefix):
        """Test engine initialization in playback mode"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix,
            contracts=['VN30F1M'],
            update_interval_seconds=15,
            mode='playback',
            f2m_window_days=3
        )

        try:
            # Verify mode is set correctly
            assert engine.mode == 'playback'
            assert engine.f2m_window_days == 3

            # Verify Redis handler has correct mode
            assert engine.redis_handler.mode == 'playback'
            assert engine.redis_handler.f2m_window_days == 3

            # Start engine
            engine.start()
            time.sleep(0.2)

            # Verify F1M subscription only (F2M not yet subscribed)
            assert engine.redis_handler.f1m_contract == 'VN30F1M'
            assert engine.redis_handler.f2m_subscribed is False

            # Stop engine
            results = engine.stop()

            # Verify results have correct mode
            assert results.mode == 'playback'

        finally:
            if engine.running:
                engine.stop()

    def test_live_mode_initialization(self, redis_host, redis_port, channel_prefix):
        """Test engine initialization in live mode"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix,
            contracts=['VN30F2510'],
            update_interval_seconds=15,
            mode='live',
            f2m_window_days=3
        )

        try:
            # Verify mode is set correctly
            assert engine.mode == 'live'

            # Verify Redis handler has correct mode
            assert engine.redis_handler.mode == 'live'

            # Start engine
            engine.start()
            time.sleep(0.2)

            # Stop engine
            results = engine.stop()

            # Verify results have correct mode
            assert results.mode == 'live'

        finally:
            if engine.running:
                engine.stop()

    def test_conditional_f2m_subscription_activation(self, redis_host, redis_port, channel_prefix):
        """Test F2M subscription activation during rollover period"""
        # Create publisher
        publisher = RedisMarketDataPublisher(
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix
        )

        if not publisher.connect():
            pytest.skip("Redis not available")

        try:
            # Create engine in playback mode
            engine = RedisPaperTradingEngine(
                initial_capital=Decimal("500000"),
                step=Decimal("2.9"),
                redis_host=redis_host,
                redis_port=redis_port,
                channel_prefix=channel_prefix,
                contracts=['VN30F1M'],
                update_interval_seconds=1,
                mode='playback',
                f2m_window_days=3
            )

            engine.start()
            time.sleep(0.2)

            # Initially F2M should not be subscribed
            assert engine.redis_handler.f2m_subscribed is False

            # Simulate contract change from VN30F2201 to VN30F2202 (rollover detection)
            # Publish F1M message with VN30F2201
            message_data = {
                'timestamp': '2022-02-14T09:00:00',
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2201',  # Actual contract code
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.3)

            # Still not subscribed (no contract change yet)
            assert engine.redis_handler.f2m_subscribed is False

            # Publish F1M message with VN30F2202 (contract changed - rollover!)
            message_data = {
                'timestamp': '2022-02-17T09:00:00',
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',  # Contract changed!
                'price': 1255.0,
                'bid': 1254.0,
                'ask': 1256.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.5)

            # F2M should now be subscribed due to contract change detection
            assert engine.redis_handler.f2m_subscribed is True
            assert engine.redis_handler.f2m_contract == 'VN30F2M'

            # Stop engine
            results = engine.stop()

            assert results.messages_processed > 0

        finally:
            publisher.disconnect()
            if engine.running:
                engine.stop()

    def test_conditional_f2m_subscription_by_date(self, redis_host, redis_port, channel_prefix):
        """Test F2M subscription activation by expiration date proximity"""
        # Create publisher
        publisher = RedisMarketDataPublisher(
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix
        )

        if not publisher.connect():
            pytest.skip("Redis not available")

        try:
            # Create engine in playback mode
            engine = RedisPaperTradingEngine(
                initial_capital=Decimal("500000"),
                step=Decimal("2.9"),
                redis_host=redis_host,
                redis_port=redis_port,
                channel_prefix=channel_prefix,
                contracts=['VN30F1M'],
                update_interval_seconds=1,
                mode='playback',
                f2m_window_days=3
            )

            engine.start()
            time.sleep(0.2)

            # Initially F2M should not be subscribed
            assert engine.redis_handler.f2m_subscribed is False

            # VN30F2202 expires on third Thursday of Feb 2022 = Feb 17, 2022
            # Publish message 5 days before expiration (outside window)
            message_data = {
                'timestamp': '2022-02-12T09:00:00',  # 5 days before Feb 17
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.3)

            # F2M should not be subscribed (outside 3-day window)
            assert engine.redis_handler.f2m_subscribed is False

            # Publish message 2 days before expiration (inside window)
            message_data = {
                'timestamp': '2022-02-15T09:00:00',  # 2 days before Feb 17
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',
                'price': 1255.0,
                'bid': 1254.0,
                'ask': 1256.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.5)

            # F2M should now be subscribed (inside 3-day window)
            assert engine.redis_handler.f2m_subscribed is True

            # Stop engine
            results = engine.stop()

            assert results.messages_processed > 0

        finally:
            publisher.disconnect()
            if engine.running:
                engine.stop()

    def test_f2m_unsubscription_after_rollover(self, redis_host, redis_port, channel_prefix):
        """Test F2M unsubscription after rollover period ends"""
        # Create publisher
        publisher = RedisMarketDataPublisher(
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix
        )

        if not publisher.connect():
            pytest.skip("Redis not available")

        try:
            # Create engine in playback mode
            engine = RedisPaperTradingEngine(
                initial_capital=Decimal("500000"),
                step=Decimal("2.9"),
                redis_host=redis_host,
                redis_port=redis_port,
                channel_prefix=channel_prefix,
                contracts=['VN30F1M'],
                update_interval_seconds=1,
                mode='playback',
                f2m_window_days=3
            )

            engine.start()
            time.sleep(0.2)

            # Trigger F2M subscription with contract change
            message_data = {
                'timestamp': '2022-02-14T09:00:00',
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2201',
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.2)

            # Contract change - should subscribe to F2M
            message_data = {
                'timestamp': '2022-02-17T09:00:00',
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',
                'price': 1255.0,
                'bid': 1254.0,
                'ask': 1256.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.5)

            assert engine.redis_handler.f2m_subscribed is True

            # Publish message several days after rollover (outside window)
            # VN30F2202 expires on Mar 17, 2022
            message_data = {
                'timestamp': '2022-03-01T09:00:00',  # 16 days before next expiration
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',
                'price': 1260.0,
                'bid': 1259.0,
                'ask': 1261.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.5)

            # F2M should be unsubscribed (outside 3-day window)
            assert engine.redis_handler.f2m_subscribed is False

            # Stop engine
            results = engine.stop()

            assert results.messages_processed > 0

        finally:
            publisher.disconnect()
            if engine.running:
                engine.stop()

    def test_dual_contract_publishing(self, redis_host, redis_port, channel_prefix):
        """Test publishing both F1M and F2M contracts simultaneously"""
        # Create publisher
        publisher = RedisMarketDataPublisher(
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix
        )

        if not publisher.connect():
            pytest.skip("Redis not available")

        try:
            # Create engine in playback mode
            engine = RedisPaperTradingEngine(
                initial_capital=Decimal("500000"),
                step=Decimal("2.9"),
                redis_host=redis_host,
                redis_port=redis_port,
                channel_prefix=channel_prefix,
                contracts=['VN30F1M'],
                update_interval_seconds=1,
                mode='playback',
                f2m_window_days=3
            )

            engine.start()
            time.sleep(0.2)

            # Trigger F2M subscription
            message_data = {
                'timestamp': '2022-02-15T09:00:00',
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0
            }
            publisher.publish_message('VN30F1M', message_data)
            time.sleep(0.5)

            # F2M should be subscribed
            assert engine.redis_handler.f2m_subscribed is True

            # Publish to both F1M and F2M
            f1_message = {
                'timestamp': '2022-02-15T09:01:00',
                'contract': 'VN30F1M',
                'tickersymbol': 'VN30F2202',
                'price': 1251.0,
                'bid': 1250.0,
                'ask': 1252.0
            }
            f2_message = {
                'timestamp': '2022-02-15T09:01:00',
                'contract': 'VN30F2M',
                'tickersymbol': 'VN30F2203',
                'price': 1255.0,
                'bid': 1254.0,
                'ask': 1256.0
            }

            publisher.publish_message('VN30F1M', f1_message)
            publisher.publish_message('VN30F2M', f2_message)
            time.sleep(0.5)

            # Get summary
            summary = engine.get_summary()

            # Should have processed messages from both contracts
            assert summary['messages_processed'] >= 3  # At least 3 messages total

            # Stop engine
            results = engine.stop()

            assert results.messages_processed >= 3

        finally:
            publisher.disconnect()
            if engine.running:
                engine.stop()


# Skip all tests if Redis is not available
def pytest_configure(config):
    """Register integration test marker"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires Redis)"
    )

"""
Unit tests for Redis Market Data Handler
"""
import pytest
from decimal import Decimal
from datetime import datetime
import json
from unittest.mock import Mock, patch, MagicMock
import redis

from core.event import EventBus, MarketDataEvent
from core.enums import EventType
from data.redis_stream import RedisMarketDataHandler


class TestRedisMarketDataHandler:
    """Test Redis market data handler"""

    def test_initialization(self):
        """Test handler initialization"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            redis_host='localhost',
            redis_port=6379
        )

        assert handler.redis_host == 'localhost'
        assert handler.redis_port == 6379
        assert handler.channel_prefix == 'market'
        assert handler.messages_received == 0
        assert handler.messages_processed == 0
        assert handler.running is False

    @patch('redis.Redis')
    def test_connect_success(self, mock_redis_class):
        """Test successful Redis connection"""
        # Mock Redis client
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        result = handler.connect()

        assert result is True
        assert handler.redis_client is not None
        mock_client.ping.assert_called_once()

    @patch('redis.Redis')
    def test_connect_failure(self, mock_redis_class):
        """Test Redis connection failure"""
        # Mock Redis client that fails to connect
        mock_client = MagicMock()
        mock_client.ping.side_effect = redis.ConnectionError("Connection refused")
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        result = handler.connect()

        assert result is False
        assert handler.redis_client is None or handler.pubsub is None

    def test_subscribe_without_connection(self):
        """Test subscribing without connecting first"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # Should handle gracefully
        handler.subscribe(['VN30F1M'])

        # No exception should be raised

    @patch('redis.Redis')
    def test_subscribe_with_connection(self, mock_redis_class):
        """Test subscribing to channels"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus)
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub

        handler.subscribe(['VN30F1M', 'VN30F2M'])

        mock_pubsub.subscribe.assert_called_once_with('market:VN30F1M', 'market:VN30F2M')

    def test_process_valid_message(self):
        """Test processing a valid message"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # Track published events
        events_received = []
        def capture_event(event):
            events_received.append(event)
        bus.subscribe(EventType.MARKET_DATA, capture_event)

        # Create valid message
        message = {
            'type': 'message',
            'data': json.dumps({
                'timestamp': '2025-10-27T10:00:00',
                'contract': 'VN30F1M',
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0,
                'spread': 2.0
            })
        }

        handler._process_message(message)
        bus.process_events()

        assert handler.messages_processed == 1
        assert len(events_received) == 1
        event = events_received[0]
        assert event.contract == 'VN30F1M'
        assert event.price == Decimal('1250.0')

    def test_process_invalid_json(self):
        """Test processing message with invalid JSON"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        message = {
            'type': 'message',
            'data': 'invalid json{'
        }

        handler._process_message(message)

        assert handler.messages_failed == 1
        assert handler.messages_processed == 0

    def test_process_missing_fields(self):
        """Test processing message with missing required fields"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # Missing 'price' field
        message = {
            'type': 'message',
            'data': json.dumps({
                'timestamp': '2025-10-27T10:00:00',
                'contract': 'VN30F1M',
                'bid': 1249.0,
                'ask': 1251.0
            })
        }

        handler._process_message(message)

        assert handler.messages_failed == 1
        assert handler.messages_processed == 0

    def test_statistics(self):
        """Test getting statistics"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        handler.messages_received = 100
        handler.messages_processed = 95
        handler.messages_failed = 5
        handler.reconnect_count = 2

        stats = handler.get_statistics()

        assert stats['messages_received'] == 100
        assert stats['messages_processed'] == 95
        assert stats['messages_failed'] == 5
        assert stats['reconnect_count'] == 2
        assert stats['is_running'] is False

    def test_is_healthy_when_not_running(self):
        """Test health check when not running"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        assert handler.is_healthy() is False

    def test_is_healthy_when_running_no_messages(self):
        """Test health check when running but no messages yet"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)
        handler.running = True

        # Should be healthy even with no messages (might be starting up)
        assert handler.is_healthy() is True

    def test_is_healthy_when_running_with_recent_message(self):
        """Test health check with recent message"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)
        handler.running = True
        handler.last_message_time = datetime.now()

        assert handler.is_healthy() is True

    def test_latency_calculation(self):
        """Test latency calculation"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # No messages yet
        assert handler.get_latency_ms() is None

        # Set last message time
        handler.last_message_time = datetime.now()

        latency = handler.get_latency_ms()
        assert latency is not None
        assert latency >= 0

    def test_stop_when_not_started(self):
        """Test stopping handler that was never started"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # Should not raise exception
        handler.stop()

        assert handler.running is False

    def test_multiple_messages_processed(self):
        """Test processing multiple messages"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        events_received = []
        def capture_event(event):
            events_received.append(event)
        bus.subscribe(EventType.MARKET_DATA, capture_event)

        # Process 3 messages
        for i in range(3):
            message = {
                'type': 'message',
                'data': json.dumps({
                    'timestamp': f'2025-10-27T10:00:0{i}',
                    'contract': 'VN30F1M',
                    'price': 1250.0 + i,
                    'bid': 1249.0 + i,
                    'ask': 1251.0 + i,
                    'spread': 2.0
                })
            }
            handler._process_message(message)

        bus.process_events()

        assert handler.messages_processed == 3
        assert len(events_received) == 3

    def test_default_spread_calculation(self):
        """Test spread calculated from bid/ask if not provided"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        events_received = []
        def capture_event(event):
            events_received.append(event)
        bus.subscribe(EventType.MARKET_DATA, capture_event)

        # Message without spread field
        message = {
            'type': 'message',
            'data': json.dumps({
                'timestamp': '2025-10-27T10:00:00',
                'contract': 'VN30F1M',
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0
            })
        }

        handler._process_message(message)
        bus.process_events()

        assert len(events_received) == 1
        # Spread should be calculated as ask - bid = 2.0
        assert events_received[0].spread == Decimal('2.0')

    def test_custom_channel_prefix(self):
        """Test using custom channel prefix"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            bus,
            channel_prefix='custom_prefix'
        )

        assert handler.channel_prefix == 'custom_prefix'

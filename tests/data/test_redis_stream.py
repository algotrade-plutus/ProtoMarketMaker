"""
Unit tests for Redis Market Data Handler

Organized into 4 test classes:
1. TestHandlerCore: Core handler functionality (mode-independent)
2. TestPlaybackMode: Playback mode specific tests
3. TestLiveMode: Live mode specific tests
4. TestConditionalF2Subscription: Conditional F2M subscription tests
"""
import pytest
from decimal import Decimal
from datetime import datetime, date
import json
from unittest.mock import Mock, patch, MagicMock
import redis

from core.event import EventBus, MarketDataEvent
from core.enums import EventType
from data.redis_stream import RedisMarketDataHandler


class TestHandlerCore:
    """
    Core handler functionality tests (mode-independent)

    Tests basic handler operations that work the same in both playback and live modes:
    - Initialization and connection
    - Message processing
    - Statistics and health monitoring
    """

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


class TestPlaybackMode:
    """
    Playback mode specific tests

    Tests handler behavior in playback mode:
    - Uses abstract contract symbols (VN30F1M, VN30F2M)
    - Subscribes to F1M initially
    - Conditionally subscribes to F2M during rollover
    - Processes tickersymbol field for rollover detection
    """

    def test_initialization_with_playback_mode(self):
        """Test handler initialization with playback mode"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='playback',
            f2m_window_days=5
        )

        assert handler.mode == 'playback'
        assert handler.f2m_window_days == 5
        assert handler.f2m_subscribed is False
        assert handler.f1m_contract is None
        assert handler.f2m_contract is None

    @patch('redis.Redis')
    def test_subscribe_f1m_only_initially(self, mock_redis_class):
        """Test that only F1M is subscribed initially in playback mode"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='playback')
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub

        handler.subscribe(['VN30F1M'])

        # Should subscribe to F1M only
        mock_pubsub.subscribe.assert_called_once_with('market:VN30F1M')
        assert handler.f1m_contract == 'VN30F1M'
        assert handler.f2m_subscribed is False

    @patch('redis.Redis')
    def test_subscribe_abstract_symbols(self, mock_redis_class):
        """Test subscribing to abstract symbols (VN30F1M, VN30F2M) in playback mode"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='playback')
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub

        # Subscribe to both abstract symbols
        handler.subscribe(['VN30F1M', 'VN30F2M'])

        # Should have called subscribe twice: once for F1M, once for F2M
        assert mock_pubsub.subscribe.call_count == 2
        # Verify F1M subscription
        assert mock_pubsub.subscribe.call_args_list[0] == (('market:VN30F1M',),)
        # Verify F2M subscription
        assert mock_pubsub.subscribe.call_args_list[1] == (('market:VN30F2M',),)

    def test_process_message_with_abstract_symbol(self):
        """Test processing message with abstract contract symbol in playback mode"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='playback')

        events_received = []
        def capture_event(event):
            events_received.append(event)
        bus.subscribe(EventType.MARKET_DATA, capture_event)

        # Message with abstract symbol
        message = {
            'type': 'message',
            'data': json.dumps({
                'timestamp': '2022-02-10T10:00:00',
                'contract': 'VN30F1M',  # Abstract symbol
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
        assert events_received[0].contract == 'VN30F1M'

    def test_process_message_with_tickersymbol_playback(self):
        """Test processing message with tickersymbol field for rollover detection in playback mode"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='playback', f2m_window_days=3)
        handler.f1m_contract = 'VN30F1M'

        events_received = []
        def capture_event(event):
            events_received.append(event)
        bus.subscribe(EventType.MARKET_DATA, capture_event)

        # Message with tickersymbol field (actual contract code)
        message = {
            'type': 'message',
            'data': json.dumps({
                'timestamp': '2022-02-15T10:00:00',  # Near expiration (Feb 17)
                'contract': 'VN30F1M',  # Abstract symbol
                'tickersymbol': 'VN30F2202',  # Actual contract code
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
        # last_f1_contract should be updated
        assert handler.last_f1_contract == 'VN30F2202'

    def test_playback_mode_default_window(self):
        """Test playback mode uses correct default F2M window"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='playback'
        )

        # Default f2m_window_days should be 3
        assert handler.f2m_window_days == 3

    def test_playback_mode_custom_window(self):
        """Test playback mode with custom F2M window"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='playback',
            f2m_window_days=7
        )

        assert handler.f2m_window_days == 7


class TestLiveMode:
    """
    Live mode specific tests

    Tests handler behavior in live mode:
    - Uses actual contract codes (VN30F2510, VN30F2511, etc.)
    - Subscribes to specific contract codes
    - No abstract symbols
    """

    def test_initialization_live_mode(self):
        """Test handler initialization with live mode"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='live'
        )

        assert handler.mode == 'live'

    @patch('redis.Redis')
    def test_subscribe_actual_contract_codes(self, mock_redis_class):
        """Test subscribing to actual contract codes in live mode"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='live')
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub

        # Subscribe to actual contract code
        handler.subscribe(['VN30F2510'])

        # Should subscribe to actual contract code
        mock_pubsub.subscribe.assert_called_once_with('market:VN30F2510')
        assert handler.f1m_contract == 'VN30F2510'

    def test_process_message_with_actual_contract(self):
        """Test processing message with actual contract code in live mode"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='live')

        events_received = []
        def capture_event(event):
            events_received.append(event)
        bus.subscribe(EventType.MARKET_DATA, capture_event)

        # Message with actual contract code
        message = {
            'type': 'message',
            'data': json.dumps({
                'timestamp': '2025-10-27T10:00:00',
                'contract': 'VN30F2510',  # Actual contract code
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
        assert events_received[0].contract == 'VN30F2510'

    @patch('redis.Redis')
    def test_subscribe_multiple_contracts_live(self, mock_redis_class):
        """Test subscribing to multiple actual contracts in live mode"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus, mode='live')
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub

        # Subscribe to multiple actual contracts
        handler.subscribe(['VN30F2510', 'VN30F2511'])

        # In live mode, multiple contracts are subscribed in a single call
        assert mock_pubsub.subscribe.call_count == 1
        # Verify both channels were subscribed
        mock_pubsub.subscribe.assert_called_once_with('market:VN30F2510', 'market:VN30F2511')

    def test_live_mode_no_f2m_conditional_subscription(self):
        """Test that live mode doesn't use conditional F2M subscription by default"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            event_bus=bus,
            mode='live'
        )

        # Live mode should not have F2M subscription logic active
        assert handler.mode == 'live'
        assert handler.f2m_subscribed is False

    def test_live_mode_channel_naming(self):
        """Test channel naming in live mode"""
        bus = EventBus()
        handler = RedisMarketDataHandler(
            bus,
            mode='live',
            channel_prefix='live_market'
        )

        assert handler.channel_prefix == 'live_market'


class TestConditionalF2Subscription:
    """
    Conditional F2M subscription tests

    Tests the automatic F2M subscription management:
    - Subscribe to F2M when entering rollover period
    - Unsubscribe from F2M when leaving rollover period
    - Rollover detection logic (contract change + expiration window)
    - Third Thursday calculation for VN30 futures
    """

    @patch('redis.Redis')
    def test_subscribe_to_f2m(self, mock_redis_class):
        """Test subscribing to F2M channel"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus)
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub
        handler.f1m_contract = 'VN30F1M'

        handler.subscribe_to_f2m()

        # Should subscribe to F2M and set flag
        mock_pubsub.subscribe.assert_called_once_with('market:VN30F2M')
        assert handler.f2m_subscribed is True
        assert handler.f2m_contract == 'VN30F2M'

    @patch('redis.Redis')
    def test_unsubscribe_from_f2m(self, mock_redis_class):
        """Test unsubscribing from F2M channel"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus)
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub
        handler.f2m_contract = 'VN30F2M'
        handler.f2m_subscribed = True

        handler.unsubscribe_from_f2m()

        # Should unsubscribe from F2M
        mock_pubsub.unsubscribe.assert_called_once_with('market:VN30F2M')
        assert handler.f2m_subscribed is False

    def test_calculate_third_thursday(self):
        """Test third Thursday calculation for various months"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # Test February 2022 (third Thursday is Feb 17)
        result = handler._calculate_third_thursday(2022, 2)
        assert result.day == 17
        assert result.month == 2
        assert result.year == 2022

        # Test March 2022 (third Thursday is Mar 17)
        result = handler._calculate_third_thursday(2022, 3)
        assert result.day == 17
        assert result.month == 3

        # Test January 2022 (third Thursday is Jan 20)
        result = handler._calculate_third_thursday(2022, 1)
        assert result.day == 20
        assert result.month == 1

    def test_detect_rollover_from_contract(self):
        """Test rollover detection from contract code changes"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus)

        # Test no rollover (same contract)
        result = handler._detect_rollover_from_contract('VN30F2202', 'VN30F2202')
        assert result is False

        # Test rollover detected (contract change)
        result = handler._detect_rollover_from_contract('VN30F2202', 'VN30F2201')
        assert result is True

        # Test first message (no previous contract)
        result = handler._detect_rollover_from_contract('VN30F2202', None)
        assert result is False

    def test_is_near_expiration(self):
        """Test expiration window detection"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, f2m_window_days=3)

        # Feb 17, 2022 is third Thursday (expiration day)
        # Test 3 days before (Feb 14) - should be True
        result = handler._is_near_expiration(date(2022, 2, 14), 'VN30F2202')
        assert result is True

        # Test 2 days before (Feb 15) - should be True
        result = handler._is_near_expiration(date(2022, 2, 15), 'VN30F2202')
        assert result is True

        # Test on expiration day (Feb 17) - should be True
        result = handler._is_near_expiration(date(2022, 2, 17), 'VN30F2202')
        assert result is True

        # Test 5 days before (Feb 12) - should be False (outside window)
        result = handler._is_near_expiration(date(2022, 2, 12), 'VN30F2202')
        assert result is False

        # Test after expiration (Feb 18) - should be False
        result = handler._is_near_expiration(date(2022, 2, 18), 'VN30F2202')
        assert result is False

    def test_should_subscribe_f2m_contract_change(self):
        """Test F2M subscription decision based on contract change"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, f2m_window_days=3)

        # Contract code change should trigger F2M subscription
        result = handler._should_subscribe_f2m(
            date(2022, 2, 10),
            'VN30F2202',
            'VN30F2201'  # Previous contract different
        )
        assert result is True

    def test_should_subscribe_f2m_near_expiration(self):
        """Test F2M subscription decision based on expiration window"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, f2m_window_days=3)

        # Within expiration window should trigger F2M subscription
        result = handler._should_subscribe_f2m(
            date(2022, 2, 15),  # 2 days before Feb 17 expiration
            'VN30F2202',
            'VN30F2202'  # Same contract
        )
        assert result is True

    def test_should_subscribe_f2m_false(self):
        """Test F2M subscription decision when not in rollover period"""
        bus = EventBus()
        handler = RedisMarketDataHandler(bus, f2m_window_days=3)

        # Outside window and same contract - should not subscribe to F2M
        result = handler._should_subscribe_f2m(
            date(2022, 2, 10),  # 7 days before expiration
            'VN30F2202',
            'VN30F2202'  # Same contract
        )
        assert result is False

    @patch('redis.Redis')
    def test_check_and_manage_f2m_subscription_activate(self, mock_redis_class):
        """Test automatic F2M subscription when entering rollover period"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus, f2m_window_days=3)
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub
        handler.f1m_contract = 'VN30F1M'

        # Check on Feb 15 (2 days before Feb 17 expiration) - should activate F2M
        handler.check_and_manage_f2m_subscription(date(2022, 2, 15), 'VN30F2202')

        # Should have subscribed to F2M
        assert handler.f2m_subscribed is True
        mock_pubsub.subscribe.assert_called_once_with('market:VN30F2M')

    @patch('redis.Redis')
    def test_check_and_manage_f2m_subscription_deactivate(self, mock_redis_class):
        """Test automatic F2M unsubscription when leaving rollover period"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_redis_class.return_value = mock_client

        bus = EventBus()
        handler = RedisMarketDataHandler(bus, f2m_window_days=3)
        handler.redis_client = mock_client
        handler.pubsub = mock_pubsub
        handler.f1m_contract = 'VN30F1M'
        handler.f2m_contract = 'VN30F2M'
        handler.f2m_subscribed = True

        # Check on Feb 10 (7 days before expiration) - should deactivate F2M
        handler.check_and_manage_f2m_subscription(date(2022, 2, 10), 'VN30F2202')

        # Should have unsubscribed from F2M
        assert handler.f2m_subscribed is False
        mock_pubsub.unsubscribe.assert_called_once_with('market:VN30F2M')

"""
Unit tests for Redis Market Data Publisher
"""
import pytest
import json
import time
import redis
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch, call
import pandas as pd

from tools.redis_publisher import RedisMarketDataPublisher


class TestRedisMarketDataPublisher:
    """Test Redis market data publisher"""

    def test_initialization(self):
        """Test publisher initialization"""
        publisher = RedisMarketDataPublisher(
            redis_host='localhost',
            redis_port=6379
        )

        assert publisher.redis_host == 'localhost'
        assert publisher.redis_port == 6379
        assert publisher.redis_client is None
        assert publisher.messages_published == 0

    @patch('tools.redis_publisher.redis.Redis')
    def test_connect_success(self, mock_redis_class):
        """Test successful Redis connection"""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client

        publisher = RedisMarketDataPublisher()
        result = publisher.connect()

        assert result is True
        assert publisher.redis_client == mock_client
        mock_client.ping.assert_called_once()

    @patch('tools.redis_publisher.redis.Redis')
    def test_connect_failure(self, mock_redis_class):
        """Test failed Redis connection"""
        mock_client = MagicMock()
        mock_client.ping.side_effect = redis.ConnectionError("Connection failed")
        mock_redis_class.return_value = mock_client

        publisher = RedisMarketDataPublisher()
        result = publisher.connect()

        assert result is False

    def test_publish_message(self):
        """Test publishing a single message"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        message_data = {
            'timestamp': '2025-10-27T10:00:00',
            'contract': 'VN30F1M',
            'price': 1250.0,
            'bid': 1249.0,
            'ask': 1251.0
        }

        publisher.publish_message('VN30F1M', message_data)

        assert publisher.messages_published == 1
        mock_client.publish.assert_called_once_with(
            'market:VN30F1M',
            json.dumps(message_data)
        )

    def test_publish_message_not_connected(self):
        """Test publishing when not connected"""
        publisher = RedisMarketDataPublisher()

        message_data = {
            'timestamp': '2025-10-27T10:00:00',
            'contract': 'VN30F1M',
            'price': 1250.0,
            'bid': 1249.0,
            'ask': 1251.0
        }

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Not connected to Redis"):
            publisher.publish_message('VN30F1M', message_data)

    @patch('tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv(self, mock_read_csv):
        """Test publishing from CSV file"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Mock CSV data
        mock_df = pd.DataFrame({
            'datetime': ['2025-10-27 10:00:00', '2025-10-27 10:00:01'],
            'tickersymbol': ['VN30F1M', 'VN30F1M'],
            'price': [1250.0, 1251.0],
            'best-bid': [1249.0, 1250.0],
            'best-ask': [1251.0, 1252.0],
            'spread': [2.0, 2.0]
        })
        mock_read_csv.return_value = mock_df

        with patch('time.sleep'):  # Skip actual sleep
            publisher.publish_from_csv('test.csv', rate_hz=10.0, max_messages=2)

        assert publisher.messages_published == 2
        assert mock_client.publish.call_count == 2

    @patch('tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv_with_loop(self, mock_read_csv):
        """Test publishing from CSV with max messages"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Mock CSV data
        mock_df = pd.DataFrame({
            'datetime': ['2025-10-27 10:00:00'],
            'tickersymbol': ['VN30F1M'],
            'price': [1250.0],
            'best-bid': [1249.0],
            'best-ask': [1251.0],
            'spread': [2.0]
        })
        mock_read_csv.return_value = mock_df

        with patch('time.sleep'):
            publisher.publish_from_csv('test.csv', max_messages=1)

        assert publisher.messages_published == 1

    def test_publish_random_data(self):
        """Test publishing random market data"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        with patch('time.sleep'):
            publisher.publish_random_data(
                contracts=['VN30F1M'],
                base_price=1250.0,
                volatility=0.5,
                duration_seconds=1,
                rate_hz=10.0
            )

        # Should have published at least 1 message
        assert publisher.messages_published >= 1
        assert mock_client.publish.call_count >= 1

    def test_publish_sine_wave(self):
        """Test publishing sine wave data"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        with patch('time.sleep'):
            publisher.publish_sine_wave(
                contracts=['VN30F1M'],
                base_price=1250.0,
                amplitude=10.0,
                period_seconds=60.0,
                duration_seconds=1,
                rate_hz=10.0
            )

        # Should have published at least 1 message
        assert publisher.messages_published >= 1
        assert mock_client.publish.call_count >= 1

    def test_get_statistics(self):
        """Test getting publisher statistics"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client
        publisher.messages_published = 100

        stats = publisher.get_statistics()

        assert stats['messages_published'] == 100
        assert stats['connected'] is True

    def test_get_statistics_not_connected(self):
        """Test getting statistics when not connected"""
        publisher = RedisMarketDataPublisher()

        stats = publisher.get_statistics()

        assert stats['messages_published'] == 0
        assert stats['connected'] is False

    @patch('tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv_file_not_found(self, mock_read_csv):
        """Test handling file not found error"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        mock_read_csv.side_effect = FileNotFoundError("File not found")

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            publisher.publish_from_csv('nonexistent.csv')

    def test_message_format(self):
        """Test that published messages have correct format"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        message_data = {
            'timestamp': '2025-10-27T10:00:00',
            'contract': 'VN30F1M',
            'price': 1250.0,
            'bid': 1249.0,
            'ask': 1251.0
        }

        publisher.publish_message('VN30F1M', message_data)

        # Get the actual call arguments
        call_args = mock_client.publish.call_args[0]
        channel = call_args[0]
        message_json = call_args[1]

        # Verify channel format
        assert channel == 'market:VN30F1M'

        # Verify message can be decoded
        decoded_message = json.loads(message_json)
        assert decoded_message == message_data

    def test_multiple_contracts(self):
        """Test publishing to multiple contracts"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        contracts = ['VN30F1M', 'VN30F2M']

        for contract in contracts:
            message_data = {
                'timestamp': datetime.now().isoformat(),
                'contract': contract,
                'price': 1250.0,
                'bid': 1249.0,
                'ask': 1251.0
            }
            publisher.publish_message(contract, message_data)

        assert publisher.messages_published == 2
        assert mock_client.publish.call_count == 2

        # Verify different channels were used
        channels_used = [call[0][0] for call in mock_client.publish.call_args_list]
        assert 'market:VN30F1M' in channels_used
        assert 'market:VN30F2M' in channels_used

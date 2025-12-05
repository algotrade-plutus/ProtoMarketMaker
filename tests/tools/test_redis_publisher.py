"""
Unit tests for Redis Market Data Publisher

Organized into 4 test classes:
- TestMergedFileMode: Backward-compatible single CSV mode
- TestDualFileMode: Separate F1M/F2M file mode
- TestDynamicRolloverDetection: Rollover detection from data
- TestConditionalF2Publishing: Conditional F2M publishing logic
"""
import pytest
import json
import time
import redis
from decimal import Decimal
from datetime import datetime, date
from unittest.mock import Mock, MagicMock, patch, call
import pandas as pd

from protomarketmaker.tools.redis_publisher import RedisMarketDataPublisher


class TestMergedFileMode:
    """
    Tests for backward-compatible merged file mode (single CSV publishing)

    This mode supports the original publisher behavior where a single CSV
    file contains all market data (potentially merged F1M and F2M data).
    """

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

    @patch('protomarketmaker.tools.redis_publisher.redis.Redis')
    def test_connect_success(self, mock_redis_class):
        """Test successful Redis connection"""
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client

        publisher = RedisMarketDataPublisher()
        result = publisher.connect()

        assert result is True
        assert publisher.redis_client == mock_client
        mock_client.ping.assert_called_once()

    @patch('protomarketmaker.tools.redis_publisher.redis.Redis')
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

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv_merged_mode(self, mock_read_csv):
        """Test publishing from single merged CSV file (backward compatibility)"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Mock merged CSV data
        mock_df = pd.DataFrame({
            'datetime': ['2022-02-07 09:00:00'],
            'tickersymbol': ['VN30F1M'],
            'price': [1250.0],
            'best-bid': [1249.0],
            'best-ask': [1251.0],
            'spread': [2.0]
        })
        mock_read_csv.return_value = mock_df

        # Call with csv_path (merged mode)
        with patch('time.sleep'):
            publisher.publish_from_csv(
                csv_path='merged.csv',
                rate_hz=10.0,
                max_messages=1
            )

        # Should have published using merged mode
        assert publisher.messages_published == 1

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv_basic(self, mock_read_csv):
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

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv_with_max_messages(self, mock_read_csv):
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

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
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

    def test_publish_from_csv_no_parameters(self):
        """Test publish_from_csv raises error when no files provided"""
        publisher = RedisMarketDataPublisher()

        # Should raise ValueError when no parameters provided
        with pytest.raises(ValueError, match="Must provide either csv_path"):
            publisher.publish_from_csv()


class TestDualFileMode:
    """
    Tests for separate F1M/F2M file mode

    This mode loads separate files for F1M and F2M data and publishes them
    with synchronized timestamps and conditional F2M publishing.
    """

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_load_separate_files(self, mock_read_csv):
        """Test loading separate F1M and F2M files"""
        publisher = RedisMarketDataPublisher()

        # Mock F1M data
        f1m_df = pd.DataFrame({
            'datetime': ['2022-02-07 09:00:00', '2022-02-07 09:00:01'],
            'tickersymbol': ['VN30F2202', 'VN30F2202'],
            'price': [1250.0, 1251.0],
            'best-bid': [1249.0, 1250.0],
            'best-ask': [1251.0, 1252.0],
            'spread': [2.0, 2.0]
        })

        # Mock F2M data
        f2m_df = pd.DataFrame({
            'datetime': ['2022-02-07 09:00:00'],
            'tickersymbol': ['VN30F2203'],
            'price': [1255.0],
            'best-bid': [1254.0],
            'best-ask': [1256.0],
            'spread': [2.0]
        })

        # Configure mock to return different DataFrames for each call
        mock_read_csv.side_effect = [f1m_df, f2m_df]

        f1m_data, f2m_data = publisher.load_separate_files(
            'f1m.csv',
            'f2m.csv',
            f2m_window_days=3
        )

        assert len(f1m_data) == 2
        assert len(f2m_data) == 1
        assert publisher.f2m_window_days == 3
        assert hasattr(publisher, 'f1m_data')
        assert hasattr(publisher, 'f2m_data')

    def test_publish_row(self):
        """Test publishing a single row from DataFrame"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Create mock row
        row = pd.Series({
            'datetime': pd.Timestamp('2022-02-07 09:00:00'),
            'tickersymbol': 'VN30F2202',
            'price': 1250.0,
            'best-bid': 1249.0,
            'best-ask': 1251.0,
            'spread': 2.0
        })

        publisher._publish_row(row, 'VN30F1M')

        # Verify message was published
        assert publisher.messages_published == 1
        mock_client.publish.assert_called_once()

        # Verify channel and message format
        call_args = mock_client.publish.call_args[0]
        channel = call_args[0]
        message_json = call_args[1]

        assert channel == 'market:VN30F1M'
        decoded = json.loads(message_json)
        assert decoded['contract'] == 'VN30F1M'
        assert decoded['price'] == 1250.0

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_publish_dual_files_basic(self, mock_read_csv):
        """Test basic dual-file publishing algorithm (no rollover)"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Mock F1M data (no rollover period - Feb 7)
        f1m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-07 09:00:00', '2022-02-07 09:00:01']),
            'tickersymbol': ['VN30F2202', 'VN30F2202'],
            'price': [1250.0, 1251.0],
            'best-bid': [1249.0, 1250.0],
            'best-ask': [1251.0, 1252.0],
            'spread': [2.0, 2.0]
        })

        # Mock F2M data
        f2m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-07 09:00:00']),
            'tickersymbol': ['VN30F2203'],
            'price': [1255.0],
            'best-bid': [1254.0],
            'best-ask': [1256.0],
            'spread': [2.0]
        })

        mock_read_csv.side_effect = [f1m_df, f2m_df]

        # Load files
        publisher.load_separate_files('f1m.csv', 'f2m.csv', f2m_window_days=3)

        # Publish
        with patch('time.sleep'):
            publisher._publish_dual_files(rate_hz=10.0, max_messages=2)

        # Should have published 2 F1M messages (no F2M since not in rollover)
        assert publisher.messages_published == 2

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_synchronized_reading(self, mock_read_csv):
        """Test F1M and F2M timestamps stay synchronized"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # F1M data with advancing timestamps
        f1m_df = pd.DataFrame({
            'datetime': pd.to_datetime([
                '2022-02-15 09:00:00',
                '2022-02-15 09:00:02',
                '2022-02-15 09:00:04'
            ]),
            'tickersymbol': ['VN30F2202', 'VN30F2202', 'VN30F2202'],
            'price': [1250.0, 1251.0, 1252.0],
            'best-bid': [1249.0, 1250.0, 1251.0],
            'best-ask': [1251.0, 1252.0, 1253.0],
            'spread': [2.0, 2.0, 2.0]
        })

        # F2M data with same timestamps (synchronized)
        f2m_df = pd.DataFrame({
            'datetime': pd.to_datetime([
                '2022-02-15 09:00:01',
                '2022-02-15 09:00:03',
                '2022-02-15 09:00:05'
            ]),
            'tickersymbol': ['VN30F2203', 'VN30F2203', 'VN30F2203'],
            'price': [1255.0, 1256.0, 1257.0],
            'best-bid': [1254.0, 1255.0, 1256.0],
            'best-ask': [1256.0, 1257.0, 1258.0],
            'spread': [2.0, 2.0, 2.0]
        })

        mock_read_csv.side_effect = [f1m_df, f2m_df]

        # Load files
        publisher.load_separate_files('f1m.csv', 'f2m.csv', f2m_window_days=3)

        # Publish (in rollover period)
        with patch('time.sleep'):
            publisher._publish_dual_files(rate_hz=10.0, max_messages=6)

        # Both F1M and F2M should be published (within rollover window)
        # Expected: 3 F1M + 3 F2M = 6 total
        assert publisher.messages_published == 6

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_f1m_always_published(self, mock_read_csv):
        """Test F1M is always published regardless of rollover status"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # F1M data outside rollover window (Feb 7)
        f1m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-07 09:00:00']),
            'tickersymbol': ['VN30F2202'],
            'price': [1250.0],
            'best-bid': [1249.0],
            'best-ask': [1251.0],
            'spread': [2.0]
        })

        # F2M data
        f2m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-07 09:00:00']),
            'tickersymbol': ['VN30F2203'],
            'price': [1255.0],
            'best-bid': [1254.0],
            'best-ask': [1256.0],
            'spread': [2.0]
        })

        mock_read_csv.side_effect = [f1m_df, f2m_df]

        # Load files
        publisher.load_separate_files('f1m.csv', 'f2m.csv', f2m_window_days=3)

        # Track published channels
        published_channels = []
        def track_publish(channel, message):
            published_channels.append(channel)
            return None
        mock_client.publish = track_publish

        # Publish
        with patch('time.sleep'):
            publisher._publish_dual_files(rate_hz=10.0, max_messages=2)

        # F1M should always be published
        assert any('VN30F1M' in ch for ch in published_channels)

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_publish_from_csv_dual_mode(self, mock_read_csv):
        """Test publish_from_csv with dual-file parameters"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Mock data
        f1m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-07 09:00:00']),
            'tickersymbol': ['VN30F2202'],
            'price': [1250.0],
            'best-bid': [1249.0],
            'best-ask': [1251.0],
            'spread': [2.0]
        })

        f2m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-07 09:00:00']),
            'tickersymbol': ['VN30F2203'],
            'price': [1255.0],
            'best-bid': [1254.0],
            'best-ask': [1256.0],
            'spread': [2.0]
        })

        mock_read_csv.side_effect = [f1m_df, f2m_df]

        # Call with dual-file parameters
        with patch('time.sleep'):
            publisher.publish_from_csv(
                f1m_csv='f1m.csv',
                f2m_csv='f2m.csv',
                f2m_window_days=3,
                rate_hz=10.0,
                max_messages=1
            )

        # Should have used dual-file mode
        assert hasattr(publisher, 'f1m_data')
        assert hasattr(publisher, 'f2m_data')
        assert publisher.messages_published >= 1


class TestDynamicRolloverDetection:
    """
    Tests for dynamic rollover detection from data

    Tests the ability to detect rollovers dynamically from:
    1. Contract code changes (VN30F2201 → VN30F2202)
    2. Third Thursday expiration date calculations
    """

    def test_calculate_third_thursday_february(self):
        """Test third Thursday calculation for February 2022"""
        publisher = RedisMarketDataPublisher()

        # Test February 2022 (third Thursday is Feb 17)
        result = publisher._calculate_third_thursday(2022, 2)
        assert result.day == 17
        assert result.month == 2
        assert result.year == 2022

    def test_calculate_third_thursday_march(self):
        """Test third Thursday calculation for March 2022"""
        publisher = RedisMarketDataPublisher()

        # Test March 2022 (third Thursday is Mar 17)
        result = publisher._calculate_third_thursday(2022, 3)
        assert result.day == 17
        assert result.month == 3
        assert result.year == 2022

    def test_calculate_third_thursday_january(self):
        """Test third Thursday calculation for January 2022"""
        publisher = RedisMarketDataPublisher()

        # Test January 2022 (third Thursday is Jan 20)
        result = publisher._calculate_third_thursday(2022, 1)
        assert result.day == 20
        assert result.month == 1
        assert result.year == 2022

    def test_detect_rollover_from_contract_no_change(self):
        """Test rollover detection when contract hasn't changed"""
        publisher = RedisMarketDataPublisher()

        # Test no rollover (same contract)
        result = publisher._detect_rollover_from_contract('VN30F2202', 'VN30F2202')
        assert result is False

    def test_detect_rollover_from_contract_with_change(self):
        """Test rollover detection when contract code changes"""
        publisher = RedisMarketDataPublisher()

        # Test rollover detected (contract change: Feb → Mar)
        result = publisher._detect_rollover_from_contract('VN30F2203', 'VN30F2202')
        assert result is True

    def test_detect_rollover_from_contract_first_row(self):
        """Test rollover detection for first row (no previous contract)"""
        publisher = RedisMarketDataPublisher()

        # Test first row (no previous contract)
        result = publisher._detect_rollover_from_contract('VN30F2202', None)
        assert result is False

    def test_is_near_expiration_inside_window(self):
        """Test expiration window detection within 3-day window"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Feb 17, 2022 is third Thursday (expiration day)
        # Test 3 days before (Feb 14) - should be True
        result = publisher._is_near_expiration(date(2022, 2, 14), 'VN30F2202')
        assert result is True

        # Test 2 days before (Feb 15) - should be True
        result = publisher._is_near_expiration(date(2022, 2, 15), 'VN30F2202')
        assert result is True

    def test_is_near_expiration_on_expiration_day(self):
        """Test expiration detection on expiration day itself"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Test on expiration day (Feb 17) - should be True
        result = publisher._is_near_expiration(date(2022, 2, 17), 'VN30F2202')
        assert result is True

    def test_is_near_expiration_outside_window(self):
        """Test expiration detection outside rollover window"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Test 5 days before (Feb 12) - should be False (outside window)
        result = publisher._is_near_expiration(date(2022, 2, 12), 'VN30F2202')
        assert result is False

    def test_is_near_expiration_after_expiration(self):
        """Test expiration detection after expiration date"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Test after expiration (Feb 18) - should be False
        result = publisher._is_near_expiration(date(2022, 2, 18), 'VN30F2202')
        assert result is False


class TestConditionalF2Publishing:
    """
    Tests for conditional F2M publishing logic

    Tests the decision-making process for when to publish F2M data
    based on rollover detection and expiration windows.
    """

    def test_should_publish_f2m_contract_change(self):
        """Test F2M publishing decision when contract changes"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Contract code change should trigger F2M publishing
        result = publisher._should_publish_f2m(
            date(2022, 2, 10),
            'VN30F2202',
            'VN30F2201'  # Previous contract different
        )
        assert result is True

    def test_should_publish_f2m_near_expiration(self):
        """Test F2M publishing decision based on expiration window"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Within expiration window should trigger F2M publishing
        result = publisher._should_publish_f2m(
            date(2022, 2, 15),  # 2 days before Feb 17 expiration
            'VN30F2202',
            'VN30F2202'  # Same contract
        )
        assert result is True

    def test_should_publish_f2m_false(self):
        """Test F2M publishing decision when not in rollover period"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Outside window and same contract - should not publish F2M
        result = publisher._should_publish_f2m(
            date(2022, 2, 10),  # 7 days before expiration
            'VN30F2202',
            'VN30F2202'  # Same contract
        )
        assert result is False

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_f2m_only_during_rollover_window(self, mock_read_csv):
        """Test F2M is only published during rollover window"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # Mock F1M data (Feb 15 - within rollover window for Feb 17 expiration)
        f1m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-15 09:00:00', '2022-02-15 09:00:01']),
            'tickersymbol': ['VN30F2202', 'VN30F2202'],
            'price': [1250.0, 1251.0],
            'best-bid': [1249.0, 1250.0],
            'best-ask': [1251.0, 1252.0],
            'spread': [2.0, 2.0]
        })

        # Mock F2M data
        f2m_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2022-02-15 09:00:00', '2022-02-15 09:00:01']),
            'tickersymbol': ['VN30F2203', 'VN30F2203'],
            'price': [1255.0, 1256.0],
            'best-bid': [1254.0, 1255.0],
            'best-ask': [1256.0, 1257.0],
            'spread': [2.0, 2.0]
        })

        mock_read_csv.side_effect = [f1m_df, f2m_df]

        # Load files
        publisher.load_separate_files('f1m.csv', 'f2m.csv', f2m_window_days=3)

        # Track channels
        published_channels = []
        def track_publish(channel, message):
            published_channels.append(channel)
            return None
        mock_client.publish = track_publish

        # Publish
        with patch('time.sleep'):
            publisher._publish_dual_files(rate_hz=10.0, max_messages=4)

        # Both F1M and F2M should be published (within rollover window)
        f1m_count = sum(1 for ch in published_channels if 'VN30F1M' in ch)
        f2m_count = sum(1 for ch in published_channels if 'VN30F2M' in ch)

        assert f1m_count == 2  # Always published
        assert f2m_count == 2  # Published during rollover

    @patch('protomarketmaker.tools.redis_publisher.pd.read_csv')
    def test_f2m_count_vs_f1m_count(self, mock_read_csv):
        """Test F2M message count is less than F1M when not always in rollover"""
        publisher = RedisMarketDataPublisher()
        mock_client = MagicMock()
        publisher.redis_client = mock_client

        # F1M data spanning both inside and outside rollover window
        # Feb 10 (outside) and Feb 15 (inside 3-day window for Feb 17)
        f1m_df = pd.DataFrame({
            'datetime': pd.to_datetime([
                '2022-02-10 09:00:00',  # Outside window
                '2022-02-15 09:00:00'   # Inside window
            ]),
            'tickersymbol': ['VN30F2202', 'VN30F2202'],
            'price': [1250.0, 1251.0],
            'best-bid': [1249.0, 1250.0],
            'best-ask': [1251.0, 1252.0],
            'spread': [2.0, 2.0]
        })

        # F2M data (matching timestamps)
        f2m_df = pd.DataFrame({
            'datetime': pd.to_datetime([
                '2022-02-10 09:00:00',
                '2022-02-15 09:00:00'
            ]),
            'tickersymbol': ['VN30F2203', 'VN30F2203'],
            'price': [1255.0, 1256.0],
            'best-bid': [1254.0, 1255.0],
            'best-ask': [1256.0, 1257.0],
            'spread': [2.0, 2.0]
        })

        mock_read_csv.side_effect = [f1m_df, f2m_df]

        # Load files
        publisher.load_separate_files('f1m.csv', 'f2m.csv', f2m_window_days=3)

        # Track channels
        published_channels = []
        def track_publish(channel, message):
            published_channels.append(channel)
            return None
        mock_client.publish = track_publish

        # Publish
        with patch('time.sleep'):
            publisher._publish_dual_files(rate_hz=10.0, max_messages=4)

        # Count messages by contract
        f1m_count = sum(1 for ch in published_channels if 'VN30F1M' in ch)
        f2m_count = sum(1 for ch in published_channels if 'VN30F2M' in ch)

        # F1M should always be published (2 messages)
        # F2M should only be published during rollover (1 message - only Feb 15)
        assert f1m_count == 2
        assert f2m_count == 1
        assert f2m_count < f1m_count  # F2M is conditional

    def test_rollover_window_boundary(self):
        """Test F2M activation exactly at window boundary"""
        publisher = RedisMarketDataPublisher()
        publisher.f2m_window_days = 3

        # Feb 17 is expiration, 3-day window starts Feb 14
        # Test exactly at boundary (Feb 14 00:00:00)
        result = publisher._is_near_expiration(date(2022, 2, 14), 'VN30F2202')
        assert result is True

        # Test one day before boundary (Feb 13)
        result = publisher._is_near_expiration(date(2022, 2, 13), 'VN30F2202')
        assert result is False

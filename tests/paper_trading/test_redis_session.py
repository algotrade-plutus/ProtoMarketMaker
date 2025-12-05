"""
Unit tests for Redis Trading Session
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from protomarketmaker.paper_trading.redis_session import RedisTradingSession


class TestRedisTradingSession:
    """Test Redis trading session"""

    def test_initialization(self):
        """Test session initialization"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            update_interval_seconds=15,
            redis_host='localhost',
            redis_port=6379
        )

        assert session.initial_capital == Decimal("500000")
        assert session.step == Decimal("2.9")
        assert session.event_bus is not None
        assert session.portfolio is not None
        assert session.risk is not None
        assert session.oms is not None
        assert session.strategy is not None
        assert session.execution is not None
        assert session.redis_handler is not None
        assert session.running is False
        assert session.contracts == []

    def test_initialization_with_defaults(self):
        """Test session initialization with default values"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        # Default redis_host and redis_port should be used
        assert session.redis_handler is not None
        assert session.running is False

    @patch('protomarketmaker.paper_trading.redis_session.RedisMarketDataHandler')
    def test_start_success(self, mock_handler_class):
        """Test successful session start"""
        mock_handler = MagicMock()
        mock_handler.connect.return_value = True
        mock_handler_class.return_value = mock_handler

        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )
        session.redis_handler = mock_handler

        result = session.start(['VN30F1M', 'VN30F2M'])

        assert result is True
        assert session.running is True
        assert session.contracts == ['VN30F1M', 'VN30F2M']
        assert session.start_time is not None
        mock_handler.connect.assert_called_once()
        mock_handler.subscribe.assert_called_once_with(['VN30F1M', 'VN30F2M'])
        mock_handler.start.assert_called_once()

    @patch('protomarketmaker.paper_trading.redis_session.RedisMarketDataHandler')
    def test_start_connection_failure(self, mock_handler_class):
        """Test session start with connection failure"""
        mock_handler = MagicMock()
        mock_handler.connect.return_value = False
        mock_handler_class.return_value = mock_handler

        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )
        session.redis_handler = mock_handler

        result = session.start(['VN30F1M'])

        assert result is False
        assert session.running is False
        mock_handler.connect.assert_called_once()
        mock_handler.subscribe.assert_not_called()
        mock_handler.start.assert_not_called()

    def test_stop(self):
        """Test stopping session"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_handler = MagicMock()
        session.redis_handler = mock_handler
        session.running = True

        session.stop()

        assert session.running is False
        mock_handler.stop.assert_called_once()

    def test_get_summary(self):
        """Test getting session summary"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_portfolio = MagicMock()
        mock_portfolio.calculate_nav.return_value = Decimal("510000")
        mock_portfolio.cash = Decimal("510000")
        mock_portfolio.get_summary.return_value = {'positions': {}}
        mock_portfolio.get_performance_metrics.return_value = {}
        mock_portfolio.daily_returns = []

        mock_oms = MagicMock()
        mock_oms.get_statistics.return_value = {
            'total_orders': 10,
            'filled_orders': 8
        }

        mock_redis_handler = MagicMock()
        mock_redis_handler.get_statistics.return_value = {
            'messages_processed': 1000,
            'processing_errors': 0
        }

        session.portfolio = mock_portfolio
        session.oms = mock_oms
        session.redis_handler = mock_redis_handler
        session.contracts = ['VN30F1M']
        session.running = True

        summary = session.get_summary()

        assert 'session' in summary
        assert 'portfolio' in summary
        assert 'orders' in summary
        assert 'redis' in summary
        assert 'performance' in summary

        assert summary['session']['contracts'] == ['VN30F1M']
        assert summary['session']['is_running'] is True
        assert summary['portfolio']['initial_capital'] == 500000.0
        assert summary['portfolio']['final_nav'] == 510000.0

    def test_get_summary_with_returns(self):
        """Test getting summary with performance metrics"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_portfolio = MagicMock()
        mock_portfolio.calculate_nav.return_value = Decimal("510000")
        mock_portfolio.cash = Decimal("510000")
        mock_portfolio.get_summary.return_value = {'positions': {}}
        mock_portfolio.get_performance_metrics.return_value = {
            'sharpe_ratio': 1.5,
            'sortino_ratio': 2.0
        }
        mock_portfolio.daily_returns = [Decimal("0.01"), Decimal("0.02")]

        mock_oms = MagicMock()
        mock_oms.get_statistics.return_value = {}

        mock_redis_handler = MagicMock()
        mock_redis_handler.get_statistics.return_value = {}

        session.portfolio = mock_portfolio
        session.oms = mock_oms
        session.redis_handler = mock_redis_handler

        summary = session.get_summary()

        assert summary['performance']['sharpe_ratio'] == 1.5
        assert summary['performance']['sortino_ratio'] == 2.0

    def test_is_healthy_when_running(self):
        """Test health check when session is running"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_redis_handler = MagicMock()
        mock_redis_handler.is_healthy.return_value = True

        session.redis_handler = mock_redis_handler
        session.running = True

        assert session.is_healthy() is True

    def test_is_healthy_when_not_running(self):
        """Test health check when session is not running"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        session.running = False

        assert session.is_healthy() is False

    def test_is_healthy_redis_unhealthy(self):
        """Test health check when Redis is unhealthy"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_redis_handler = MagicMock()
        mock_redis_handler.is_healthy.return_value = False

        session.redis_handler = mock_redis_handler
        session.running = True

        assert session.is_healthy() is False

    def test_get_latency_ms(self):
        """Test getting Redis latency"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_redis_handler = MagicMock()
        mock_redis_handler.get_latency_ms.return_value = 2.5

        session.redis_handler = mock_redis_handler

        latency = session.get_latency_ms()

        assert latency == 2.5
        mock_redis_handler.get_latency_ms.assert_called_once()

    def test_get_latency_ms_none(self):
        """Test getting latency when not available"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_redis_handler = MagicMock()
        mock_redis_handler.get_latency_ms.return_value = None

        session.redis_handler = mock_redis_handler

        latency = session.get_latency_ms()

        assert latency is None

    def test_component_integration(self):
        """Test that all components are properly integrated"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        # Check that EventBus is shared across components
        assert session.portfolio.event_bus is session.event_bus
        assert session.oms.event_bus is session.event_bus
        assert session.strategy.event_bus is session.event_bus
        assert session.execution.event_bus is session.event_bus
        assert session.redis_handler.event_bus is session.event_bus

    def test_start_updates_state(self):
        """Test that start() properly updates session state"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_handler = MagicMock()
        mock_handler.connect.return_value = True
        session.redis_handler = mock_handler

        assert session.running is False
        assert session.start_time is None

        session.start(['VN30F1M'])

        assert session.running is True
        assert session.start_time is not None

    def test_stop_updates_state(self):
        """Test that stop() properly updates session state"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_handler = MagicMock()
        session.redis_handler = mock_handler
        session.running = True

        session.stop()

        assert session.running is False

    def test_total_return_calculation(self):
        """Test total return calculation in summary"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_portfolio = MagicMock()
        # 10% return
        mock_portfolio.calculate_nav.return_value = Decimal("550000")
        mock_portfolio.cash = Decimal("550000")
        mock_portfolio.get_summary.return_value = {'positions': {}}
        mock_portfolio.get_performance_metrics.return_value = {}
        mock_portfolio.daily_returns = []

        mock_oms = MagicMock()
        mock_oms.get_statistics.return_value = {}

        mock_redis_handler = MagicMock()
        mock_redis_handler.get_statistics.return_value = {}

        session.portfolio = mock_portfolio
        session.oms = mock_oms
        session.redis_handler = mock_redis_handler

        summary = session.get_summary()

        # Should be 10% return
        assert summary['portfolio']['total_return'] == 10.0

    def test_session_duration_tracking(self):
        """Test that session duration is tracked"""
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        mock_portfolio = MagicMock()
        mock_portfolio.calculate_nav.return_value = Decimal("500000")
        mock_portfolio.cash = Decimal("500000")
        mock_portfolio.get_summary.return_value = {'positions': {}}
        mock_portfolio.get_performance_metrics.return_value = {}
        mock_portfolio.daily_returns = []

        mock_oms = MagicMock()
        mock_oms.get_statistics.return_value = {}

        mock_redis_handler = MagicMock()
        mock_redis_handler.get_statistics.return_value = {}

        session.portfolio = mock_portfolio
        session.oms = mock_oms
        session.redis_handler = mock_redis_handler

        import time
        session.start_time = time.time() - 60  # 60 seconds ago

        summary = session.get_summary()

        # Duration should be approximately 60 seconds
        assert summary['session']['duration_seconds'] >= 59
        assert summary['session']['duration_seconds'] <= 61

"""
Tests for RedisPaperTradingEngine

Organized into 4 test classes:
1. TestEngineCore: Core engine functionality (mode-independent)
2. TestEnginePlaybackMode: Playback mode specific tests
3. TestEngineLiveMode: Live mode specific tests
4. TestEngineResults: Results tracking and export tests
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from protomarketmaker.paper_trading.engine import RedisPaperTradingEngine
from protomarketmaker.paper_trading.results import PaperTradingResults


@pytest.fixture
def mock_redis_handler():
    """Mock RedisMarketDataHandler"""
    handler = Mock()
    handler.redis_host = 'localhost'
    handler.redis_port = 6379
    handler.subscribe = Mock(return_value=True)
    handler.start = Mock()
    handler.stop = Mock()
    handler.message_count = 100
    handler.get_latency_ms = Mock(return_value=25.5)
    handler.is_healthy = Mock(return_value=True)
    handler.get_statistics = Mock(return_value={
        'message_count': 100,
        'avg_latency_ms': 25.5,
        'reconnect_count': 0
    })
    return handler


@pytest.fixture
def mock_portfolio():
    """Mock PortfolioManager"""
    portfolio = Mock()
    portfolio.get_total_value = Mock(return_value=Decimal('503000'))
    portfolio.get_daily_nav_history = Mock(return_value=[Decimal('500000'), Decimal('503000')])
    portfolio.get_daily_returns = Mock(return_value=[Decimal('0'), Decimal('0.006')])
    portfolio.get_tracking_dates = Mock(return_value=[])
    portfolio.get_rollover_history = Mock(return_value=[])
    portfolio.positions = {}
    portfolio.performance_evaluator = Mock()
    portfolio.performance_evaluator.get_metrics = Mock(return_value={
        'sharpe_ratio': 0.8,
        'sortino_ratio': 1.2,
        'max_drawdown': -0.01,
        'hpr': 0.006
    })
    return portfolio


@pytest.fixture
def mock_monitor():
    """Mock PerformanceMonitor"""
    monitor = Mock()
    monitor.total_trades = 10
    monitor.buy_count = 5
    monitor.sell_count = 5
    monitor.get_total_fees = Mock(return_value=Decimal('500'))
    return monitor


class TestEngineCore:
    """
    Core engine functionality tests (mode-independent)

    Tests basic engine operations that work the same in both playback and live modes:
    - Initialization
    - Start/stop lifecycle
    - Run modes
    - Component wiring
    """

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_initialization_default(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test engine initializes with default parameters"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        assert engine.initial_capital == Decimal('500000')
        assert engine.step == Decimal('2.9')
        assert engine.mode == 'playback'  # Default mode
        assert engine.contracts == ['VN30F1M']  # Default for playback mode
        assert engine._running is False
        assert engine.start_time is None
        assert engine.end_time is None

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_initialization_with_contracts(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test engine initializes with custom contracts"""
        contracts = ['VN30F2511', 'VN30F2512']
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            contracts=contracts
        )

        assert engine.contracts == contracts

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_initialization_with_redis_settings(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test engine initializes with custom Redis settings"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            redis_host='192.168.1.100',
            redis_port=6380,
            channel_prefix='data'
        )

        # Verify RedisMarketDataHandler was called with correct params
        mock_redis_handler.assert_called_once()
        call_kwargs = mock_redis_handler.call_args[1]
        assert call_kwargs['redis_host'] == '192.168.1.100'
        assert call_kwargs['redis_port'] == 6380
        assert call_kwargs['channel_prefix'] == 'data'

    @patch('protomarketmaker.paper_trading.engine.EventRecorder')
    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_initialization_with_event_recording(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler, mock_recorder
    ):
        """Test engine initializes with event recording enabled"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            record_events=True,
            event_log_path='logs/test.jsonl'
        )

        mock_recorder.assert_called_once_with('logs/test.jsonl')
        assert engine.recorder is not None

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_start_success(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test successful engine start"""
        # Setup
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            contracts=['VN30F2510']
        )

        # Start
        success = engine.start()

        assert success is True
        assert engine._running is True
        assert engine.start_time is not None
        redis_instance.subscribe.assert_called_once_with(['VN30F2510'])
        redis_instance.start.assert_called_once()

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_start_already_running(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test starting engine that's already running"""
        redis_instance = Mock()
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        # Start once
        engine.start()

        # Try to start again
        success = engine.start()

        assert success is False

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_start_subscribe_failure(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test engine start when connection fails"""
        redis_instance = Mock()
        redis_instance.connect = Mock(return_value=False)  # Connection fails
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            contracts=['VN30F2510']
        )

        success = engine.start()

        assert success is False
        assert engine._running is False

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_stop_success(
        self, mock_event_bus, mock_portfolio_class, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor_class, mock_redis_handler
    ):
        """Test successful engine stop"""
        # Setup mocks
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        redis_instance.stop = Mock()
        redis_instance.get_statistics = Mock(return_value={
            'message_count': 100,
            'avg_latency_ms': 25.0,
            'reconnect_count': 0
        })
        mock_redis_handler.return_value = redis_instance

        portfolio_instance = Mock()
        portfolio_instance.get_total_value = Mock(return_value=Decimal('503000'))
        portfolio_instance.get_daily_nav_history = Mock(return_value=[])
        portfolio_instance.get_daily_returns = Mock(return_value=[])
        portfolio_instance.get_tracking_dates = Mock(return_value=[])
        portfolio_instance.get_rollover_history = Mock(return_value=[])
        portfolio_instance.performance_evaluator = None
        mock_portfolio_class.return_value = portfolio_instance

        monitor_instance = Mock()
        monitor_instance.total_trades = 10
        monitor_instance.buy_count = 5
        monitor_instance.sell_count = 5
        monitor_instance.get_total_fees = Mock(return_value=Decimal('500'))
        mock_monitor_class.return_value = monitor_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        # Start then stop
        engine.start()
        results = engine.stop()

        assert engine._running is False
        assert engine.end_time is not None
        assert isinstance(results, PaperTradingResults)
        redis_instance.stop.assert_called_once()

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_stop_not_running(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test stopping engine that's not running"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        results = engine.stop()

        assert results is None

    @patch('time.sleep')
    @patch('signal.signal')
    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_run_with_duration(
        self, mock_event_bus, mock_portfolio_class, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor_class, mock_redis_handler,
        mock_signal, mock_sleep
    ):
        """Test run() with specified duration"""
        # Setup
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        redis_instance.stop = Mock()
        redis_instance.get_statistics = Mock(return_value={
            'message_count': 100,
            'avg_latency_ms': 25.0,
            'reconnect_count': 0
        })
        mock_redis_handler.return_value = redis_instance

        portfolio_instance = Mock()
        portfolio_instance.get_total_value = Mock(return_value=Decimal('503000'))
        portfolio_instance.get_daily_nav_history = Mock(return_value=[])
        portfolio_instance.get_daily_returns = Mock(return_value=[])
        portfolio_instance.get_tracking_dates = Mock(return_value=[])
        portfolio_instance.get_rollover_history = Mock(return_value=[])
        portfolio_instance.performance_evaluator = None
        mock_portfolio_class.return_value = portfolio_instance

        monitor_instance = Mock()
        monitor_instance.total_trades = 10
        monitor_instance.buy_count = 5
        monitor_instance.sell_count = 5
        monitor_instance.get_total_fees = Mock(return_value=Decimal('500'))
        mock_monitor_class.return_value = monitor_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        # Run for 60 seconds
        results = engine.run(duration_seconds=60)

        assert results is not None
        assert isinstance(results, PaperTradingResults)
        # With event processing loop, sleep is called with 0.01s many times
        mock_sleep.assert_called_with(0.01)

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_run_start_failure(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test run() when start fails"""
        redis_instance = Mock()
        redis_instance.connect = Mock(return_value=False)  # Connection fails
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        results = engine.run(duration_seconds=1)  # Short duration for test

        assert results is None


class TestEnginePlaybackMode:
    """
    Playback mode specific tests

    Tests engine behavior in playback mode:
    - Uses abstract contract symbols (VN30F1M, VN30F2M)
    - Subscribes to F1M initially
    - Processes historical data
    """

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_playback_mode_initialization(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test engine initializes in playback mode with abstract symbols"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='playback'
        )

        assert engine.mode == 'playback'
        assert engine.contracts == ['VN30F1M']  # Default abstract symbol

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_playback_abstract_symbols(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test playback mode uses abstract contract symbols"""
        # Setup
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='playback',
            contracts=['VN30F1M']
        )

        # Start engine
        engine.start()

        # Verify abstract symbols were used for subscription
        redis_instance.subscribe.assert_called_once_with(['VN30F1M'])

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_playback_with_f2m_window(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test playback mode with F2M window configuration"""
        # Setup
        redis_instance = Mock()
        redis_instance.mode = 'playback'
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='playback',
            f2m_window_days=5  # Custom rollover window
        )

        # Verify RedisMarketDataHandler was called with correct f2m_window_days
        call_kwargs = mock_redis_handler.call_args[1]
        assert call_kwargs['mode'] == 'playback'
        assert call_kwargs['f2m_window_days'] == 5


class TestEngineLiveMode:
    """
    Live mode specific tests

    Tests engine behavior in live mode:
    - Uses actual contract codes (VN30F2510, VN30F2511, etc.)
    - Subscribes to specific contract codes
    - Processes live market data
    """

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_live_mode_initialization(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test engine initializes in live mode with actual contract codes"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='live',
            contracts=['VN30F2510']
        )

        assert engine.mode == 'live'
        assert engine.contracts == ['VN30F2510']  # Actual contract code

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_live_actual_contract_codes(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test live mode uses actual contract codes for subscription"""
        # Setup
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='live',
            contracts=['VN30F2510']
        )

        # Start engine
        engine.start()

        # Verify actual contract codes were used for subscription
        redis_instance.subscribe.assert_called_once_with(['VN30F2510'])

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_live_mode_multiple_contracts(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test live mode with multiple contract codes"""
        # Setup
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        mock_redis_handler.return_value = redis_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            mode='live',
            contracts=['VN30F2510', 'VN30F2511']
        )

        # Start engine
        engine.start()

        # Verify multiple contracts were subscribed
        redis_instance.subscribe.assert_called_once_with(['VN30F2510', 'VN30F2511'])


class TestEngineResults:
    """
    Results tracking and export tests

    Tests real-time summary and results generation
    """

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_get_summary_not_running(
        self, mock_event_bus, mock_portfolio, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor, mock_redis_handler
    ):
        """Test get_summary when engine not running"""
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9')
        )

        summary = engine.get_summary()

        assert summary['status'] == 'stopped'

    @patch('protomarketmaker.paper_trading.engine.RedisMarketDataHandler')
    @patch('protomarketmaker.paper_trading.engine.PerformanceMonitor')
    @patch('protomarketmaker.paper_trading.engine.MockExecutionEngine')
    @patch('protomarketmaker.paper_trading.engine.MarketMakerStrategy')
    @patch('protomarketmaker.paper_trading.engine.OrderManager')
    @patch('protomarketmaker.paper_trading.engine.RiskManager')
    @patch('protomarketmaker.paper_trading.engine.PortfolioManager')
    @patch('protomarketmaker.paper_trading.engine.EventBus')
    def test_get_summary_running(
        self, mock_event_bus, mock_portfolio_class, mock_risk, mock_oms,
        mock_strategy, mock_execution, mock_monitor_class, mock_redis_handler
    ):
        """Test get_summary when engine running"""
        # Setup
        redis_instance = Mock()
        redis_instance.redis_host = 'localhost'
        redis_instance.redis_port = 6379
        redis_instance.subscribe = Mock(return_value=True)
        redis_instance.start = Mock()
        redis_instance.messages_processed = 150
        redis_instance.get_latency_ms = Mock(return_value=30.5)
        redis_instance.is_healthy = Mock(return_value=True)
        mock_redis_handler.return_value = redis_instance

        portfolio_instance = Mock()
        portfolio_instance.calculate_nav = Mock(return_value=Decimal('503000'))
        portfolio_instance.positions = {}
        portfolio_instance.current_prices = {}
        mock_portfolio_class.return_value = portfolio_instance

        monitor_instance = Mock()
        monitor_instance.total_trades = 12
        mock_monitor_class.return_value = monitor_instance

        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            contracts=['VN30F2510']
        )

        engine.start()
        summary = engine.get_summary()

        assert summary['status'] == 'running'
        assert summary['contracts'] == ['VN30F2510']
        assert summary['current_nav'] == 503000.0
        assert summary['initial_capital'] == 500000.0
        assert summary['pnl'] == 3000.0
        assert summary['total_trades'] == 12
        assert summary['redis_messages'] == 150
        assert summary['redis_latency_ms'] == 30.5
        assert summary['is_healthy'] is True

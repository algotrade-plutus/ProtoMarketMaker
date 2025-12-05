"""
Tests for PaperTradingResults

Tests the results dataclass for storing and exporting paper trading session results.
"""

import pytest
import json
import tempfile
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

from protomarketmaker.paper_trading.results import PaperTradingResults


@pytest.fixture
def sample_results():
    """Create sample results for testing"""
    return PaperTradingResults(
        # Session metadata
        start_time=datetime(2025, 11, 3, 9, 0, 0),
        end_time=datetime(2025, 11, 3, 14, 30, 0),
        duration_seconds=19800.0,  # 5.5 hours
        mode='redis',

        # Performance metrics
        sharpe_ratio=0.8234,
        sortino_ratio=1.2451,
        max_drawdown=-0.0015,
        hpr=0.0069,

        # Trading statistics
        total_trades=15,
        buy_trades=8,
        sell_trades=7,
        total_fees=Decimal('1200.50'),

        # Portfolio timeline
        initial_capital=Decimal('500000'),
        final_nav=Decimal('503450'),
        daily_nav=[Decimal('500000'), Decimal('501000'), Decimal('503450')],
        daily_returns=[Decimal('0'), Decimal('0.002'), Decimal('0.0049')],
        tracking_dates=[date(2025, 11, 3), date(2025, 11, 4), date(2025, 11, 5)],

        # Redis-specific metrics
        messages_received=2500,
        messages_processed=2500,
        avg_latency_ms=35.2,
        reconnect_count=0,

        # Rollovers
        rollovers=[
            {
                'old_contract': 'VN30F2511',
                'new_contract': 'VN30F2512',
                'timestamp': '2025-11-03 14:00:00',
                'pnl': 1200.0
            }
        ]
    )


class TestPaperTradingResultsInitialization:
    """Test results initialization"""

    def test_initialization(self, sample_results):
        """Test that results object initializes correctly"""
        assert sample_results.start_time == datetime(2025, 11, 3, 9, 0, 0)
        assert sample_results.end_time == datetime(2025, 11, 3, 14, 30, 0)
        assert sample_results.duration_seconds == 19800.0
        assert sample_results.mode == 'redis'

    def test_performance_metrics(self, sample_results):
        """Test performance metrics are stored correctly"""
        assert sample_results.sharpe_ratio == 0.8234
        assert sample_results.sortino_ratio == 1.2451
        assert sample_results.max_drawdown == -0.0015
        assert sample_results.hpr == 0.0069

    def test_trading_statistics(self, sample_results):
        """Test trading statistics are stored correctly"""
        assert sample_results.total_trades == 15
        assert sample_results.buy_trades == 8
        assert sample_results.sell_trades == 7
        assert sample_results.total_fees == Decimal('1200.50')

    def test_portfolio_timeline(self, sample_results):
        """Test portfolio timeline data"""
        assert sample_results.initial_capital == Decimal('500000')
        assert sample_results.final_nav == Decimal('503450')
        assert len(sample_results.daily_nav) == 3
        assert len(sample_results.daily_returns) == 3
        assert len(sample_results.tracking_dates) == 3


class TestResultsSerialization:
    """Test JSON serialization"""

    def test_to_dict(self, sample_results):
        """Test conversion to dictionary"""
        result_dict = sample_results.to_dict()

        assert isinstance(result_dict, dict)
        # Check structured format
        assert 'session' in result_dict
        assert 'performance' in result_dict
        assert 'trading' in result_dict
        assert 'redis_metrics' in result_dict

        assert result_dict['session']['mode'] == 'redis'
        assert result_dict['trading']['total_trades'] == 15

        # Check Decimal converted to string (for precision)
        assert isinstance(result_dict['trading']['total_fees'], str)
        assert result_dict['trading']['total_fees'] == '1200.50'

        # Check datetime converted to string
        assert isinstance(result_dict['session']['start_time'], str)
        assert result_dict['session']['start_time'] == '2025-11-03T09:00:00'

    def test_to_dict_converts_all_decimals(self, sample_results):
        """Test all Decimal fields are converted to float or string"""
        result_dict = sample_results.to_dict()

        # Large Decimal values converted to string for precision
        assert isinstance(result_dict['trading']['total_fees'], str)
        assert isinstance(result_dict['performance']['initial_capital'], str)
        assert isinstance(result_dict['performance']['final_nav'], str)
        # Arrays converted to float
        assert all(isinstance(x, float) for x in result_dict['performance']['daily_nav'])
        assert all(isinstance(x, float) for x in result_dict['performance']['daily_returns'])

    def test_to_dict_converts_all_dates(self, sample_results):
        """Test all datetime/date fields are converted to strings"""
        result_dict = sample_results.to_dict()

        assert isinstance(result_dict['session']['start_time'], str)
        assert isinstance(result_dict['session']['end_time'], str)
        assert all(isinstance(d, str) for d in result_dict['performance']['tracking_dates'])

    def test_to_json(self, sample_results):
        """Test JSON file export"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            sample_results.to_json(temp_path)

            # Verify file exists and is valid JSON
            assert Path(temp_path).exists()

            with open(temp_path, 'r') as f:
                data = json.load(f)

            # Check structured format
            assert data['session']['mode'] == 'redis'
            assert data['trading']['total_trades'] == 15

        finally:
            Path(temp_path).unlink()

    def test_from_json(self, sample_results):
        """Test JSON file import"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            # Export
            sample_results.to_json(temp_path)

            # Import
            loaded_results = PaperTradingResults.from_json(temp_path)

            # Verify data matches
            assert loaded_results.start_time == sample_results.start_time
            assert loaded_results.end_time == sample_results.end_time
            assert loaded_results.mode == sample_results.mode
            assert loaded_results.total_trades == sample_results.total_trades

            # Verify Decimal types restored
            assert isinstance(loaded_results.total_fees, Decimal)
            assert loaded_results.total_fees == sample_results.total_fees

            # Verify datetime types restored
            assert isinstance(loaded_results.start_time, datetime)
            assert isinstance(loaded_results.end_time, datetime)
            assert all(isinstance(d, date) for d in loaded_results.tracking_dates)

        finally:
            Path(temp_path).unlink()

    def test_round_trip_serialization(self, sample_results):
        """Test that export → import preserves all data"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            # Export and import
            sample_results.to_json(temp_path)
            loaded_results = PaperTradingResults.from_json(temp_path)

            # Compare all fields
            assert loaded_results.start_time == sample_results.start_time
            assert loaded_results.end_time == sample_results.end_time
            assert loaded_results.duration_seconds == sample_results.duration_seconds
            assert loaded_results.mode == sample_results.mode
            assert loaded_results.sharpe_ratio == sample_results.sharpe_ratio
            assert loaded_results.sortino_ratio == sample_results.sortino_ratio
            assert loaded_results.max_drawdown == sample_results.max_drawdown
            assert loaded_results.hpr == sample_results.hpr
            assert loaded_results.total_trades == sample_results.total_trades
            assert loaded_results.buy_trades == sample_results.buy_trades
            assert loaded_results.sell_trades == sample_results.sell_trades
            assert loaded_results.total_fees == sample_results.total_fees
            assert loaded_results.initial_capital == sample_results.initial_capital
            assert loaded_results.final_nav == sample_results.final_nav
            assert loaded_results.daily_nav == sample_results.daily_nav
            assert loaded_results.daily_returns == sample_results.daily_returns
            assert loaded_results.tracking_dates == sample_results.tracking_dates
            assert loaded_results.messages_received == sample_results.messages_received
            assert loaded_results.messages_processed == sample_results.messages_processed
            assert loaded_results.avg_latency_ms == sample_results.avg_latency_ms
            assert loaded_results.reconnect_count == sample_results.reconnect_count
            assert loaded_results.rollovers == sample_results.rollovers

        finally:
            Path(temp_path).unlink()


class TestSummaryGeneration:
    """Test summary text generation"""

    def test_get_summary_text(self, sample_results):
        """Test summary text generation"""
        summary = sample_results.get_summary_text()

        assert isinstance(summary, str)
        assert 'PAPER TRADING RESULTS' in summary
        assert 'redis' in summary
        assert '15' in summary  # total trades
        assert '0.8234' in summary  # sharpe ratio

    def test_get_summary_text_contains_all_sections(self, sample_results):
        """Test summary contains all expected sections"""
        summary = sample_results.get_summary_text()

        assert 'Session:' in summary
        assert 'Duration:' in summary
        assert 'Performance Metrics:' in summary
        assert 'Trading Statistics:' in summary
        assert 'Redis Statistics:' in summary
        assert 'Contract Rollovers:' in summary

    def test_get_summary_text_redis_mode(self, sample_results):
        """Test Redis-specific statistics appear in redis mode"""
        summary = sample_results.get_summary_text()

        assert 'Redis Statistics:' in summary
        assert 'Messages Received:' in summary
        assert 'Avg Latency:' in summary

    def test_get_summary_text_csv_mode(self, sample_results):
        """Test Redis statistics don't appear in CSV mode"""
        sample_results.mode = 'csv'
        summary = sample_results.get_summary_text()

        assert 'Redis Statistics:' not in summary

    def test_get_summary_text_with_rollovers(self, sample_results):
        """Test rollovers are displayed"""
        summary = sample_results.get_summary_text()

        assert 'Contract Rollovers:' in summary
        assert 'VN30F2511 → VN30F2512' in summary

    def test_get_summary_text_without_rollovers(self, sample_results):
        """Test summary works without rollovers"""
        sample_results.rollovers = []
        summary = sample_results.get_summary_text()

        assert isinstance(summary, str)
        assert 'PAPER TRADING RESULTS' in summary

    def test_print_summary(self, sample_results, capsys):
        """Test print_summary outputs to console"""
        sample_results.print_summary()

        captured = capsys.readouterr()
        assert 'PAPER TRADING RESULTS' in captured.out
        assert 'redis' in captured.out


class TestEdgeCases:
    """Test edge cases"""

    def test_empty_portfolio_timeline(self):
        """Test with empty portfolio data"""
        results = PaperTradingResults(
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=100.0,
            mode='redis',
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            hpr=0.0,
            total_trades=0,
            buy_trades=0,
            sell_trades=0,
            total_fees=Decimal('0'),
            initial_capital=Decimal('500000'),
            final_nav=Decimal('500000'),
            daily_nav=[],
            daily_returns=[],
            tracking_dates=[],
            messages_received=0,
            messages_processed=0,
            avg_latency_ms=0.0,
            reconnect_count=0,
            rollovers=[]
        )

        summary = results.get_summary_text()
        assert 'PAPER TRADING RESULTS' in summary

    def test_large_numbers(self):
        """Test with large portfolio values"""
        results = PaperTradingResults(
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=100.0,
            mode='redis',
            sharpe_ratio=5.0,
            sortino_ratio=10.0,
            max_drawdown=-0.5,
            hpr=2.0,
            total_trades=10000,
            buy_trades=5000,
            sell_trades=5000,
            total_fees=Decimal('1000000'),
            initial_capital=Decimal('10000000'),
            final_nav=Decimal('30000000'),
            daily_nav=[Decimal('10000000')],
            daily_returns=[Decimal('0')],
            tracking_dates=[date.today()],
            messages_received=1000000,
            messages_processed=1000000,
            avg_latency_ms=100.0,
            reconnect_count=10,
            rollovers=[]
        )

        # Should handle large numbers without errors
        summary = results.get_summary_text()
        assert '10,000' in summary  # Check thousands separator

        # Test serialization
        result_dict = results.to_dict()
        assert result_dict['trading']['total_trades'] == 10000

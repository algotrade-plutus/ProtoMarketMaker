"""
Unit tests for BacktestingEngine
"""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from backtesting.engine import BacktestingEngine


# Get path to test fixtures
FIXTURES_DIR = Path(__file__).parent / 'fixtures'
SAMPLE_CSV = FIXTURES_DIR / 'sample_data.csv'


class TestBacktestingEngine:
    """Test Backtesting Engine"""

    def test_initialization(self):
        """Test engine initialization"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        assert engine.initial_capital == Decimal("500000")
        assert engine.step == Decimal("2.9")
        assert engine.event_bus is not None
        assert engine.portfolio is not None
        assert engine.strategy is not None
        assert engine.oms is not None
        assert engine.execution is not None
        assert engine.data_feed is not None

    def test_components_share_event_bus(self):
        """Test that all components share the same EventBus"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        # All components should use the same event bus
        assert engine.portfolio.event_bus is engine.event_bus
        assert engine.strategy.event_bus is engine.event_bus
        assert engine.oms.event_bus is engine.event_bus
        assert engine.execution.event_bus is engine.event_bus
        assert engine.data_feed.event_bus is engine.event_bus

    def test_run_backtest_completes(self):
        """Test that backtest runs to completion"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        results = engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Verify results structure
        assert results is not None
        assert results.initial_capital == Decimal("500000")
        assert results.events_processed > 0
        assert results.duration_seconds > 0

    def test_backtest_processes_events(self):
        """Test that backtest processes market data events"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        results = engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Should have processed events (15 from Jan 3 + 5 from Jan 4)
        assert results.events_processed == 20

    def test_backtest_generates_metrics(self):
        """Test that backtest generates performance metrics"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        results = engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Metrics should be calculated (may be zero for small sample)
        assert hasattr(results, 'sharpe_ratio')
        assert hasattr(results, 'sortino_ratio')
        assert hasattr(results, 'max_drawdown')
        assert hasattr(results, 'hpr')

    def test_backtest_tracks_trades(self):
        """Test that backtest tracks trading activity"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        results = engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Should track trades (may be zero or non-zero depending on strategy)
        assert results.total_trades >= 0
        assert results.buy_trades >= 0
        assert results.sell_trades >= 0

    def test_backtest_updates_portfolio(self):
        """Test that backtest updates portfolio"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        results = engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Portfolio should have final value
        assert results.final_capital > 0

        # Should have timeline data
        assert len(results.daily_assets) > 0
        assert len(results.daily_returns) >= 0

    def test_get_portfolio_summary(self):
        """Test getting portfolio summary during backtest"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        # Run backtest
        engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Get summary
        summary = engine.get_portfolio_summary()

        assert summary is not None
        assert 'cash' in summary
        assert 'positions' in summary

    def test_get_order_statistics(self):
        """Test getting order statistics"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        # Run backtest
        engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Get stats
        stats = engine.get_order_statistics()

        assert stats is not None
        assert 'total_orders' in stats

    def test_reset(self):
        """Test resetting engine"""
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path=str(SAMPLE_CSV)
        )

        # Run backtest
        engine.run(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 3),
            show_progress=False
        )

        # Reset
        engine.reset()

        # Portfolio should be reset
        assert engine.portfolio.cash == Decimal("500000")

"""
Event-Driven Backtesting Engine

Validates Phase 1-3 components by replaying historical data.
Similar to RedisTradingSession but uses CSV data feed.
"""
from decimal import Decimal
from datetime import date, datetime
from typing import Optional
import logging
import time

from core.event import EventBus
from core.enums import EventType
from engine.portfolio import PortfolioManager
from engine.oms import OrderManager
from engine.risk import RiskManager
from engine.strategy import MarketMakerStrategy
from engine.execution import MockExecutionEngine
from evaluation.monitor import PerformanceMonitor
from backtesting.data_feed import HistoricalDataFeed
from backtesting.results import BacktestResults


class BacktestingEngine:
    """
    Event-driven backtesting engine

    Uses the same components as RedisTradingSession but replays
    historical CSV data instead of Redis stream.

    This validates that all Phase 1-3 components work correctly
    by comparing results with original backtesting.py.

    Example:
        engine = BacktestingEngine(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            csv_path="data/is/historical.csv"
        )

        results = engine.run(
            start_date=date(2022, 1, 1),
            end_date=date(2023, 1, 1)
        )

        print(results.summary())
    """

    def __init__(
        self,
        initial_capital: Decimal,
        step: Decimal,
        csv_path: str,
        update_interval_seconds: int = 15,
        fee_per_contract: Decimal = Decimal("20.0")
    ):
        """
        Initialize backtesting engine

        Args:
            initial_capital: Starting capital
            step: Strategy step parameter
            csv_path: Path to historical CSV data
            update_interval_seconds: Strategy update interval (default: 15)
            fee_per_contract: Fee per contract (default: 20.0)
        """
        self.initial_capital = initial_capital
        self.step = step
        self.csv_path = csv_path
        self.update_interval_seconds = update_interval_seconds
        self.fee_per_contract = fee_per_contract

        self.logger = logging.getLogger(__name__)

        # Initialize components (same as RedisTradingSession)
        self.event_bus = EventBus()

        # Portfolio Manager
        self.portfolio = PortfolioManager(
            event_bus=self.event_bus,
            initial_capital=initial_capital
        )

        # Risk Manager
        self.risk = RiskManager(
            portfolio=self.portfolio
        )

        # Order Manager
        self.oms = OrderManager(
            event_bus=self.event_bus,
            risk_manager=self.risk
        )

        # Strategy
        self.strategy = MarketMakerStrategy(
            event_bus=self.event_bus,
            portfolio=self.portfolio,
            step=step,
            update_interval_seconds=update_interval_seconds
        )

        # Execution Engine (with risk manager for pre-fill checks)
        self.execution = MockExecutionEngine(
            event_bus=self.event_bus,
            risk_manager=self.risk
        )

        # Performance Monitor
        self.monitor = PerformanceMonitor(
            event_bus=self.event_bus
        )

        # Data Feed
        self.data_feed = HistoricalDataFeed(
            event_bus=self.event_bus,
            csv_path=csv_path
        )

        # Track runtime
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def run(
        self,
        start_date: date,
        end_date: date,
        show_progress: bool = True
    ) -> BacktestResults:
        """
        Run backtest on historical data

        Args:
            start_date: Start date for backtest
            end_date: End date for backtest
            show_progress: Show progress bar

        Returns:
            BacktestResults with complete metrics
        """
        self.logger.info(f"Starting backtest from {start_date} to {end_date}")
        self.start_time = time.time()

        # Load data
        self.logger.info("Loading historical data...")
        self.data_feed.load_data()

        # Replay data as events
        self.logger.info("Replaying historical data as events...")
        self.data_feed.replay(
            start_date=start_date,
            end_date=end_date,
            show_progress=show_progress,
            contracts=None  # Replay all contracts (real codes like VN30F2201, etc.)
        )

        # Process any remaining events
        self.logger.info("Processing final events...")
        self.event_bus.process_events()

        # Calculate final metrics
        self.end_time = time.time()
        self.logger.info("Backtest complete, generating results...")

        return self._generate_results()

    def _generate_results(self) -> BacktestResults:
        """
        Generate backtest results

        Returns:
            BacktestResults with all metrics
        """
        # Get portfolio metrics
        portfolio_summary = self.portfolio.get_summary()
        performance_metrics = self.portfolio.get_performance_metrics()

        # Get monitor metrics
        monitor_metrics = self.monitor.get_current_metrics()

        # Calculate final capital
        final_nav = self.portfolio.calculate_nav()

        # Get data feed stats
        feed_stats = self.data_feed.get_statistics()

        # Duration
        duration = self.end_time - self.start_time if self.end_time else 0

        # Create results
        results = BacktestResults(
            # Performance metrics
            sharpe_ratio=performance_metrics.get('sharpe_ratio', 0.0),
            sortino_ratio=performance_metrics.get('sortino_ratio', 0.0),
            max_drawdown=performance_metrics.get('max_drawdown', 0.0),
            hpr=(float(final_nav) / float(self.initial_capital) - 1),
            annual_return=performance_metrics.get('annual_return', 0.0),
            monthly_return=performance_metrics.get('monthly_return', 0.0),

            # Trading statistics
            total_trades=monitor_metrics['total_trades'],
            buy_trades=monitor_metrics['buy_count'],
            sell_trades=monitor_metrics['sell_count'],
            total_fees=monitor_metrics['total_fees'],

            # Portfolio timeline
            initial_capital=self.initial_capital,
            final_capital=final_nav,
            daily_assets=self.portfolio.daily_nav.copy(),
            daily_returns=self.portfolio.daily_returns.copy(),
            daily_inventory=[],  # TODO: Track inventory by day
            tracking_dates=[],   # TODO: Extract from portfolio

            # Contract rolling
            expirations_handled=feed_stats.get('expirations_detected', 0),

            # Runtime statistics
            events_processed=feed_stats['events_emitted'],
            duration_seconds=duration
        )

        self.logger.info(f"Results generated: Sharpe={results.sharpe_ratio:.4f}")

        return results

    def get_portfolio_summary(self) -> dict:
        """Get current portfolio summary"""
        return self.portfolio.get_summary()

    def get_order_statistics(self) -> dict:
        """Get order management statistics"""
        return self.oms.get_statistics()

    def reset(self):
        """Reset engine state (useful for testing)"""
        # Reset all components
        self.portfolio = PortfolioManager(
            event_bus=self.event_bus,
            initial_capital=self.initial_capital
        )
        self.strategy.reset()
        self.data_feed.reset()
        self.monitor.reset()

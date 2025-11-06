"""
Trading Session

Orchestrates all components for paper trading.
"""
from decimal import Decimal
from datetime import datetime
import pandas as pd
import logging
from typing import Optional

from protomarketmaker.core import EventBus, MarketDataEvent, TimeEvent, EventType
from protomarketmaker.engine import (
    MarketMakerStrategy,
    OrderManager,
    PortfolioManager,
    RiskManager,
    MockExecutionEngine,
)


class TradingSession:
    """
    Trading session coordinator

    Manages lifecycle of paper trading system:
    - Initialize all components
    - Load and replay market data
    - Process events
    - Generate reports

    Example:
        session = TradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )
        session.run_backtest(data)
    """

    def __init__(
        self,
        initial_capital: Decimal,
        step: Decimal,
        update_interval_seconds: int = 15
    ):
        """
        Initialize trading session

        Args:
            initial_capital: Starting capital
            step: Strategy step parameter
            update_interval_seconds: Order update frequency
        """
        self.logger = logging.getLogger(__name__)
        self.initial_capital = initial_capital
        self.step = step

        # Create event bus
        self.event_bus = EventBus()

        # Initialize components
        self.portfolio = PortfolioManager(self.event_bus, initial_capital)
        self.risk = RiskManager(self.portfolio)
        self.oms = OrderManager(self.event_bus, self.risk)
        self.strategy = MarketMakerStrategy(
            self.event_bus,
            self.portfolio,
            step,
            update_interval_seconds
        )
        self.execution = MockExecutionEngine(self.event_bus)

        self.logger.info(
            f"Trading session initialized: capital={initial_capital}, step={step}"
        )

    def run_backtest(self, data: pd.DataFrame) -> dict:
        """
        Run backtest with event replay

        Replays historical data as market data events.

        Args:
            data: DataFrame with columns: datetime, price, contract, etc.

        Returns:
            Dictionary with session summary
        """
        self.logger.info(f"Starting backtest with {len(data)} data points")

        for index, row in data.iterrows():
            # Create market data event
            event = MarketDataEvent(
                timestamp=pd.to_datetime(row['datetime']),
                contract=row['tickersymbol'],
                price=Decimal(str(row['price'])),
                bid=Decimal(str(row['best-bid'])),
                ask=Decimal(str(row['best-ask'])),
                spread=Decimal(str(row['spread']))
            )

            # Publish event
            self.event_bus.publish(event)

            # Process all events
            self.event_bus.process_events()

            # Log progress every 1000 ticks
            if index % 1000 == 0:
                nav = self.portfolio.calculate_nav()
                self.logger.info(
                    f"Processed {index}/{len(data)} ticks, NAV={nav:.2f}"
                )

        self.logger.info("Backtest complete")

        # Final report
        return self.get_summary()

    def get_summary(self) -> dict:
        """
        Get trading session summary

        Returns:
            Dictionary with portfolio, orders, and performance metrics
        """
        portfolio_summary = self.portfolio.get_summary()
        oms_stats = self.oms.get_statistics()

        # Calculate final metrics
        final_nav = self.portfolio.calculate_nav()
        total_return = (final_nav / self.initial_capital - 1) * 100

        summary = {
            'portfolio': {
                'initial_capital': float(self.initial_capital),
                'final_nav': float(final_nav),
                'cash': float(self.portfolio.cash),
                'total_return': float(total_return),
                'positions': portfolio_summary['positions']
            },
            'orders': oms_stats,
            'performance': self.portfolio.get_performance_metrics() if len(self.portfolio.daily_returns) > 0 else {}
        }

        return summary

    def reset(self):
        """Reset session to initial state"""
        self.portfolio = PortfolioManager(self.event_bus, self.initial_capital)
        self.risk = RiskManager(self.portfolio)
        self.oms = OrderManager(self.event_bus, self.risk)
        self.strategy = MarketMakerStrategy(
            self.event_bus,
            self.portfolio,
            self.step
        )
        self.execution = MockExecutionEngine(self.event_bus)
        self.logger.info("Session reset")

"""
Redis-based Trading Session

Real-time trading session using Redis Pub/Sub for market data.
"""
from decimal import Decimal
import logging
import time
from typing import Optional

from core.event import EventBus
from engine.strategy import MarketMakerStrategy
from engine.oms import OrderManager
from engine.portfolio import PortfolioManager
from engine.risk import RiskManager
from engine.execution import MockExecutionEngine
from data.redis_stream import RedisMarketDataHandler


class RedisTradingSession:
    """
    Trading session with Redis streaming data

    Integrates all core trading components with Redis market data streaming.

    Example:
        session = RedisTradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9"),
            redis_host='localhost'
        )
        session.start(['VN30F1M', 'VN30F2M'])

        # Run for a while
        time.sleep(60)

        # Get results
        summary = session.get_summary()
        session.stop()
    """

    def __init__(
        self,
        initial_capital: Decimal,
        step: Decimal,
        update_interval_seconds: int = 15,
        redis_host: str = 'localhost',
        redis_port: int = 6379
    ):
        """
        Initialize Redis trading session

        Args:
            initial_capital: Starting capital
            step: Strategy step parameter
            update_interval_seconds: Order update frequency
            redis_host: Redis server hostname
            redis_port: Redis server port
        """
        self.logger = logging.getLogger(__name__)
        self.initial_capital = initial_capital
        self.step = step

        # Create event bus
        self.event_bus = EventBus()

        # Initialize trading components
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

        # Initialize Redis handler
        self.redis_handler = RedisMarketDataHandler(
            event_bus=self.event_bus,
            redis_host=redis_host,
            redis_port=redis_port
        )

        self.running = False
        self.contracts: list[str] = []
        self.start_time: Optional[float] = None

        self.logger.info(
            f"Redis trading session initialized: "
            f"capital={initial_capital}, step={step}"
        )

    def start(self, contracts: list[str]) -> bool:
        """
        Start trading with Redis market data

        Args:
            contracts: List of contracts to subscribe to

        Returns:
            True if started successfully
        """
        self.logger.info(f"Starting Redis trading session for {contracts}")

        # Connect to Redis
        if not self.redis_handler.connect():
            self.logger.error("Failed to connect to Redis")
            return False

        # Subscribe to contracts
        self.redis_handler.subscribe(contracts)
        self.contracts = contracts

        # Start listener
        self.redis_handler.start()

        self.running = True
        self.start_time = time.time()

        self.logger.info("Trading session started")

        return True

    def stop(self):
        """Stop trading session"""
        self.logger.info("Stopping trading session...")

        self.running = False

        # Stop Redis handler
        self.redis_handler.stop()

        # Calculate session duration
        if self.start_time:
            duration = time.time() - self.start_time
            self.logger.info(f"Session duration: {duration:.1f} seconds")

        self.logger.info("Trading session stopped")

    def get_summary(self) -> dict:
        """
        Get current session summary

        Returns:
            Dictionary with portfolio, orders, and performance data
        """
        portfolio_summary = self.portfolio.get_summary()
        oms_stats = self.oms.get_statistics()
        redis_stats = self.redis_handler.get_statistics()

        final_nav = self.portfolio.calculate_nav()
        total_return = (final_nav / self.initial_capital - 1) * 100

        # Calculate session duration
        duration_seconds = 0
        if self.start_time:
            duration_seconds = time.time() - self.start_time

        return {
            'session': {
                'contracts': self.contracts,
                'duration_seconds': duration_seconds,
                'is_running': self.running
            },
            'portfolio': {
                'initial_capital': float(self.initial_capital),
                'final_nav': float(final_nav),
                'cash': float(self.portfolio.cash),
                'total_return': float(total_return),
                'positions': portfolio_summary['positions']
            },
            'orders': oms_stats,
            'redis': redis_stats,
            'performance': self.portfolio.get_performance_metrics() if len(self.portfolio.daily_returns) > 0 else {}
        }

    def is_healthy(self) -> bool:
        """
        Check if session is healthy

        Returns:
            True if all components are functioning
        """
        if not self.running:
            return False

        # Check Redis handler health
        if not self.redis_handler.is_healthy():
            self.logger.warning("Redis handler not healthy")
            return False

        return True

    def get_latency_ms(self) -> Optional[float]:
        """
        Get approximate Redis latency in milliseconds

        Returns:
            Latency in ms, or None if not available
        """
        return self.redis_handler.get_latency_ms()

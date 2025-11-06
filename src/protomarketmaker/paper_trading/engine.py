"""
Redis-Based Paper Trading Engine

This module provides the main engine for paper trading with Redis streaming data.
Mirrors BacktestingEngine architecture for consistency.
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime
import signal

from protomarketmaker.core import EventBus, EventType
from protomarketmaker.engine import (
    PortfolioManager,
    OrderManager,
    RiskManager,
    MarketMakerStrategy,
    MockExecutionEngine,
)
from protomarketmaker.evaluation import PerformanceMonitor
from protomarketmaker.data import RedisMarketDataHandler
from .recorder import EventRecorder
from .results import PaperTradingResults


class RedisPaperTradingEngine:
    """
    Redis-based paper trading engine

    Mirrors BacktestingEngine architecture but uses RedisMarketDataHandler
    for live/playback market data streaming instead of HistoricalDataFeed.

    Example:
        engine = RedisPaperTradingEngine(
            initial_capital=Decimal('500000'),
            step=Decimal('2.9'),
            redis_host='localhost',
            redis_port=6379,
            contracts=['VN30F2510', 'VN30F2511']  # Use resolved codes
        )

        # Run for 1 hour
        results = engine.run(duration_seconds=3600)

        # Or run indefinitely (Ctrl+C to stop)
        engine.start()
        # ... trading in background ...
        engine.stop()
    """

    def __init__(
        self,
        initial_capital: Decimal,
        step: Decimal,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        channel_prefix: str = 'market',
        contracts: list = None,
        update_interval_seconds: int = 15,
        record_events: bool = False,
        event_log_path: str = None,
        mode: str = 'playback',
        f2m_window_days: int = 3,
        audit_log_enabled: bool = False,
        audit_log_path: str = None
    ):
        """
        Initialize paper trading engine with Redis data source

        Args:
            initial_capital: Starting capital (e.g., 500,000 VND)
            step: Strategy step parameter (e.g., 2.9)
            redis_host: Redis server hostname (localhost for playback, prod IP for live)
            redis_port: Redis server port (default 6379)
            channel_prefix: Channel prefix (e.g., 'market' for 'market:VN30F2510')
            contracts: List of contracts to trade
                       - playback mode: abstract symbols (VN30F1M)
                       - live mode: resolved codes (VN30F2510)
            update_interval_seconds: Signal generation interval (default 15s)
            record_events: Whether to record events to JSONL for debugging
            event_log_path: Path to event log file (if record_events=True)
            mode: Operating mode - 'playback' (testing) or 'live' (production)
            f2m_window_days: Days before expiration to subscribe to F2M (default: 3)
            audit_log_enabled: Whether to enable audit logging (signals, fills, rollovers)
            audit_log_path: Path to audit log file (if audit_log_enabled=True)
        """
        self.initial_capital = initial_capital
        self.step = step
        self.mode = mode
        self.f2m_window_days = f2m_window_days
        self.contracts = contracts or (['VN30F1M'] if mode == 'playback' else ['VN30F2510'])
        self.start_time = None
        self.end_time = None
        self._running = False

        # Core event bus
        self.event_bus = EventBus()

        # Initialize all trading components
        self.portfolio = PortfolioManager(
            event_bus=self.event_bus,
            initial_capital=initial_capital
        )

        self.risk = RiskManager(portfolio=self.portfolio)

        self.oms = OrderManager(
            event_bus=self.event_bus,
            risk_manager=self.risk
        )

        self.strategy = MarketMakerStrategy(
            event_bus=self.event_bus,
            portfolio=self.portfolio,
            step=step,
            update_interval_seconds=update_interval_seconds
        )

        self.execution = MockExecutionEngine(
            event_bus=self.event_bus,
            risk_manager=self.risk
        )

        self.monitor = PerformanceMonitor(
            event_bus=self.event_bus
        )

        # Redis market data handler (mode-aware with conditional F2M subscription)
        self.redis_handler = RedisMarketDataHandler(
            event_bus=self.event_bus,
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix,
            mode=mode,
            f2m_window_days=f2m_window_days
        )

        # Optional event recording for debugging
        self.recorder = None
        if record_events:
            self.recorder = EventRecorder(event_log_path or 'logs/paper_trading/events.jsonl')
            # Subscribe recorder to all event types
            for event_type in EventType:
                self.event_bus.subscribe(event_type, self.recorder.record)

        # Optional audit logging for signals, fills, and rollovers
        self.audit_logger = None
        if audit_log_enabled:
            from paper_trading.audit_logger import AuditLogger
            self.audit_logger = AuditLogger(
                log_path=audit_log_path or 'logs/audit/session.log',
                enabled=True
            )
            # Subscribe to signal and fill events
            self.event_bus.subscribe(EventType.SIGNAL, self._log_signal)
            self.event_bus.subscribe(EventType.FILL, self._log_fill)

    @property
    def running(self) -> bool:
        """Check if engine is running"""
        return self._running

    def start(self) -> bool:
        """
        Start live trading (non-blocking)

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            print("Engine already running")
            return False

        try:
            # Open event recorder
            if self.recorder:
                self.recorder.__enter__()

            # Connect to Redis
            if not self.redis_handler.connect():
                print("Failed to connect to Redis")
                return False

            # Subscribe to contracts
            self.redis_handler.subscribe(self.contracts)

            # Start Redis handler (background thread)
            self.redis_handler.start()

            self.start_time = datetime.now()
            self._running = True

            print(f"Paper trading started at {self.start_time}")
            print(f"Contracts: {self.contracts}")
            print(f"Redis: {self.redis_handler.redis_host}:{self.redis_handler.redis_port}")

            return True

        except Exception as e:
            print(f"Failed to start engine: {e}")
            return False

    def _log_signal(self, event):
        """Log signal event to audit log"""
        if self.audit_logger:
            # Extract signal data from event
            timestamp = event.timestamp
            contract = event.contract
            reason = getattr(event, 'reason', 'TIME_ELAPSED')

            # Get current market price from portfolio's price cache
            # This contains the last matched price from market data
            market_price = self.portfolio.current_prices.get(contract, Decimal('0'))

            # Get current inventory (get_position always returns a Position object)
            position = self.portfolio.get_position(contract)
            inventory = position.quantity

            # Get bid/ask from signal event (strategy already calculated these)
            bid_price = event.bid_price
            ask_price = event.ask_price
            spread = ask_price - bid_price

            self.audit_logger.log_signal(
                timestamp=timestamp,
                reason=reason,
                market_price=market_price,
                bid_price=bid_price,
                ask_price=ask_price,
                spread=spread,
                inventory=inventory,
                contract=contract
            )

    def _log_fill(self, event):
        """Log fill event to audit log"""
        if self.audit_logger:
            # Extract fill data from event (FillEvent has these fields directly)
            timestamp = event.timestamp
            contract = event.contract
            side = event.side  # Already a string: "BID" or "ASK"
            price = event.fill_price
            qty = event.fill_quantity

            # Get inventory after the fill
            position = self.portfolio.get_position(contract)
            inv_after = position.quantity
            inv_price_after = position.average_price

            # Calculate inv_before (reverse the fill)
            # Map "BID" -> BUY, "ASK" -> SELL
            if side == "BID":
                inv_before = inv_after - qty
            else:  # "ASK"
                inv_before = inv_after + qty

            # Get inventory price before (simplified)
            inv_price_before = inv_price_after  # Approximation

            # Determine fill type
            if inv_before == 0:
                fill_type = f"OPEN_{'LONG' if side == 'BID' else 'SHORT'}"
            elif inv_after == 0:
                fill_type = f"COVER_{'SHORT' if side == 'BID' else 'LONG'}"
            else:
                fill_type = "MODIFY"

            self.audit_logger.log_fill(
                timestamp=timestamp,
                side=side,
                price=price,
                qty=qty,
                inv_before=inv_before,
                inv_after=inv_after,
                inv_price_before=inv_price_before,
                inv_price_after=inv_price_after,
                fill_type=fill_type,
                contract=contract
            )

    def stop(self) -> PaperTradingResults:
        """
        Stop trading and generate results

        Returns:
            PaperTradingResults object with all metrics
        """
        if not self._running:
            print("Engine not running")
            return None

        self.end_time = datetime.now()

        # Stop Redis handler
        self.redis_handler.stop()

        # Close event recorder
        if self.recorder:
            self.recorder.__exit__(None, None, None)

        # Generate results
        results = self._generate_results()

        # Log audit summary and close
        if self.audit_logger:
            self.audit_logger.log_summary(
                total_signals=self.audit_logger.signal_count,
                total_fills=self.audit_logger.fill_count,
                total_rollovers=self.audit_logger.rollover_count,
                initial_capital=self.initial_capital,
                final_nav=results.final_nav if results else self.initial_capital,
                hpr=results.hpr if results else Decimal('0')
            )
            self.audit_logger.close()

        self._running = False

        print(f"Paper trading stopped at {self.end_time}")
        print(f"Duration: {results.duration_seconds:.0f}s ({results.duration_seconds/3600:.1f}h)")

        return results

    def run(self, duration_seconds: Optional[int] = None) -> PaperTradingResults:
        """
        Run trading for specified duration (blocking)

        Args:
            duration_seconds: Duration to run (None = indefinite, Ctrl+C to stop)

        Returns:
            PaperTradingResults object
        """
        import time

        # Setup Ctrl+C handler
        def signal_handler(sig, frame):
            print("\nStopping...")
            if self._running:
                self.stop()

        signal.signal(signal.SIGINT, signal_handler)

        # Start trading
        if not self.start():
            return None

        try:
            if duration_seconds:
                print(f"Running for {duration_seconds}s...")
                start_time = time.time()
                while self._running and (time.time() - start_time) < duration_seconds:
                    # Process queued events to dispatch to handlers
                    self.event_bus.process_events()
                    time.sleep(0.01)  # 10ms processing interval
            else:
                print("Running indefinitely (Ctrl+C to stop)...")
                while self._running:
                    # Process queued events to dispatch to handlers
                    self.event_bus.process_events()
                    time.sleep(0.01)  # 10ms processing interval
        except KeyboardInterrupt:
            pass

        # Stop and generate results
        if self._running:
            return self.stop()
        else:
            return None

    def get_summary(self) -> dict:
        """
        Get real-time summary while running

        Returns:
            Dictionary with current status
        """
        if not self._running:
            # Return basic info when stopped
            return {
                "status": "stopped",
                "messages_processed": self.redis_handler.messages_processed if self.redis_handler else 0
            }

        return {
            "status": "running",
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "contracts": self.contracts,
            "current_nav": float(self.portfolio.calculate_nav()),
            "initial_capital": float(self.initial_capital),
            "pnl": float(self.portfolio.calculate_nav() - self.initial_capital),
            "positions": {
                contract: {
                    "quantity": pos.quantity,
                    "average_price": float(pos.average_price),
                    "current_price": float(self.portfolio.current_prices.get(contract, pos.average_price))
                }
                for contract, pos in self.portfolio.positions.items()
            },
            "total_trades": self.monitor.total_trades,
            "messages_processed": self.redis_handler.messages_processed,
            "redis_messages": self.redis_handler.messages_processed,  # Backward compatibility
            "redis_latency_ms": self.redis_handler.get_latency_ms(),
            "is_healthy": self.redis_handler.is_healthy()
        }

    def _generate_results(self) -> PaperTradingResults:
        """
        Generate comprehensive results object

        Returns:
            PaperTradingResults with all metrics
        """
        duration = (self.end_time - self.start_time).total_seconds()

        # Get PLUTUS metrics from portfolio
        plutus_metrics = {}
        if hasattr(self.portfolio, 'performance_evaluator') and self.portfolio.performance_evaluator:
            plutus_metrics = self.portfolio.performance_evaluator.get_metrics()

        # Get Redis statistics
        redis_stats = self.redis_handler.get_statistics()

        return PaperTradingResults(
            # Session metadata
            start_time=self.start_time,
            end_time=self.end_time,
            duration_seconds=duration,
            mode=self.mode,  # playback or live

            # Performance metrics (from PLUTUS)
            sharpe_ratio=plutus_metrics.get('sharpe_ratio', 0.0),
            sortino_ratio=plutus_metrics.get('sortino_ratio', 0.0),
            max_drawdown=plutus_metrics.get('max_drawdown', 0.0),
            hpr=plutus_metrics.get('hpr', 0.0),

            # Trading statistics (from Monitor)
            total_trades=self.monitor.total_trades,
            buy_trades=self.monitor.buy_count if hasattr(self.monitor, 'buy_count') else 0,
            sell_trades=self.monitor.sell_count if hasattr(self.monitor, 'sell_count') else 0,
            total_fees=self.monitor.get_total_fees() if hasattr(self.monitor, 'get_total_fees') else Decimal('0'),

            # Portfolio timeline (from Portfolio)
            initial_capital=self.initial_capital,
            final_nav=self.portfolio.calculate_nav(),
            daily_nav=self.portfolio.daily_nav if hasattr(self.portfolio, 'daily_nav') else [],
            daily_returns=self.portfolio.daily_returns if hasattr(self.portfolio, 'daily_returns') else [],
            tracking_dates=self.portfolio.tracking_dates if hasattr(self.portfolio, 'tracking_dates') else [],

            # Redis-specific metrics
            messages_received=redis_stats.get('messages_received', 0),
            messages_processed=redis_stats.get('messages_processed', 0),
            avg_latency_ms=redis_stats.get('avg_latency_ms', 0.0),
            reconnect_count=redis_stats.get('reconnect_count', 0),

            # Contract rollover tracking
            rollovers=self.portfolio.get_rollover_history() if hasattr(self.portfolio, 'get_rollover_history') else []
        )

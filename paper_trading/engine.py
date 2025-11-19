"""
Redis-Based Paper Trading Engine

This module provides the main engine for paper trading with Redis streaming data.
Mirrors BacktestingEngine architecture for consistency.
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime
import signal

from core.event import EventBus
from core.enums import EventType
from engine.portfolio import PortfolioManager
from engine.oms import OrderManager
from engine.risk import RiskManager
from engine.strategy import MarketMakerStrategy
from engine.execution import MockExecutionEngine
from engine.paperbroker_execution import PaperBrokerExecutionEngine
from connectors.paperbroker_connector import PaperBrokerConnector
from evaluation.monitor import PerformanceMonitor
from data.redis_stream import RedisMarketDataHandler
from paper_trading.recorder import EventRecorder
from paper_trading.results import PaperTradingResults


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
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        redis_decode_responses: bool = True,
        channel_prefix: str = 'market',
        contracts: list = None,
        update_interval_seconds: int = 15,
        record_events: bool = False,
        event_log_path: str = None,
        mode: str = 'playback',
        f2m_window_days: int = 3,
        audit_log_enabled: bool = False,
        audit_log_path: str = None,
        execution_mode: str = 'mock',
        paperbroker_config: dict = None
    ):
        """
        Initialize paper trading engine with Redis data source

        Args:
            initial_capital: Starting capital (e.g., 500,000 VND)
            step: Strategy step parameter (e.g., 2.9)
            redis_host: Redis server hostname (localhost for playback, prod IP for live)
            redis_port: Redis server port (default 6379)
            redis_db: Redis database number (default 0)
            redis_password: Redis password for authentication (None if no auth required)
            redis_decode_responses: Whether to decode responses to strings (default True)
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
            execution_mode: Execution mode - 'mock' or 'paperbroker' (default: 'mock')
            paperbroker_config: Configuration dict for PaperBroker connection (if execution_mode='paperbroker')
                               Should contain: fix_host, fix_port, sender_comp_id, target_comp_id,
                               username, password, rest_base_url, default_sub_account
        """
        self.initial_capital = initial_capital
        self.step = step
        self.mode = mode
        self.f2m_window_days = f2m_window_days
        self.contracts = contracts or (['VN30F1M'] if mode == 'playback' else ['VN30F2510'])
        self.start_time = None
        self.end_time = None
        self._running = False
        self.execution_mode = execution_mode
        self.paperbroker_config = paperbroker_config
        self.event_count = 0  # Counter for periodic status logging

        # Track closed positions for PnL statistics
        self.closed_positions = []  # List of dicts with {contract, pnl_points, pnl_pct, timestamp}
        self.total_realized_pnl_points = Decimal('0')  # Cumulative PnL in points

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

        # Initialize execution engine based on mode
        if execution_mode == 'paperbroker':
            if not paperbroker_config:
                raise ValueError("paperbroker_config required when execution_mode='paperbroker'")

            # Create PaperBroker connector
            self.connector = PaperBrokerConnector(
                event_bus=self.event_bus,
                fix_host=paperbroker_config['fix_host'],
                fix_port=paperbroker_config['fix_port'],
                sender_comp_id=paperbroker_config['sender_comp_id'],
                target_comp_id=paperbroker_config['target_comp_id'],
                username=paperbroker_config['username'],
                password=paperbroker_config['password'],
                rest_base_url=paperbroker_config['rest_base_url'],
                default_sub_account=paperbroker_config.get('default_sub_account', 'D1'),
                fee_rate=paperbroker_config.get('fee_rate', 0.002)
            )

            # Create PaperBroker execution engine
            self.execution = PaperBrokerExecutionEngine(
                event_bus=self.event_bus,
                connector=self.connector,
                risk_manager=self.risk,
                order_timeout_seconds=paperbroker_config.get('order_timeout_seconds', 60),
                max_pending_orders=paperbroker_config.get('max_pending_orders', 10)
            )
        else:
            # Default to mock execution
            self.connector = None
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
            redis_db=redis_db,
            redis_password=redis_password,
            redis_decode_responses=redis_decode_responses,
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

            # Connect to PaperBroker if using real execution
            if self.execution_mode == 'paperbroker' and self.connector:
                print(f"Connecting to PaperBroker FIX server...")
                if not self.connector.connect(timeout=10):
                    print("Failed to connect to PaperBroker FIX server")
                    return False
                print(f"Connected to PaperBroker successfully")

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
            print(f"Execution mode: {self.execution_mode}")
            print(f"Contracts: {self.contracts}")
            print(f"Redis: {self.redis_handler.redis_host}:{self.redis_handler.redis_port}")

            return True

        except Exception as e:
            print(f"Failed to start engine: {e}")
            return False

    def _log_signal(self, event):
        """Log signal event to audit log and position status"""
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

        # Log position and order status at INFO level (after signal processing)
        self._log_position_status_after_signal(event)

    def _log_fill(self, event):
        """Log fill event to audit log"""
        # IMPORTANT: Portfolio has ALREADY updated the position by the time we get here
        # (both portfolio and this method subscribe to FILL events)
        # So we need to reverse-calculate the BEFORE state from the AFTER state

        position_after = self.portfolio.get_position(event.contract)
        inv_after = position_after.quantity  # This is AFTER the fill
        entry_price_after = position_after.average_price

        # Extract fill data
        contract = event.contract
        side = event.side  # "BID" or "ASK"
        price = event.fill_price
        qty = event.fill_quantity

        # Reverse-calculate BEFORE state from AFTER state
        # BID = buy (inventory increased), ASK = sell (inventory decreased)
        if side == "BID":
            inv_before = inv_after - qty  # Undo the increase
        else:  # ASK
            inv_before = inv_after + qty  # Undo the decrease

        # Calculate entry price before (for closed positions)
        if inv_before != 0:
            # Had a position before - use the entry price
            # (simplified: assume avg price doesn't change much for non-closing fills)
            entry_price_before = entry_price_after
        else:
            # Was flat before, just opened a position
            entry_price_before = price  # The fill price is the entry

        if self.audit_logger:
            # Get inventory price after (if position closed, it's 0)
            if inv_after == 0:
                inv_price_after = Decimal('0')
            else:
                inv_price_after = entry_price_after

            inv_price_before = entry_price_before if inv_before != 0 else Decimal('0')

            # Determine fill type
            if inv_before == 0:
                fill_type = f"OPEN_{'LONG' if side == 'BID' else 'SHORT'}"
            elif inv_after == 0:
                fill_type = f"COVER_{'SHORT' if side == 'BID' else 'LONG'}"
            else:
                fill_type = "MODIFY"

            self.audit_logger.log_fill(
                timestamp=event.timestamp,
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

        # Log PnL status at INFO level (pass all needed state)
        self._log_pnl_status_after_fill(event, entry_price_before, inv_before, entry_price_after, inv_after)

    def _log_position_status_after_signal(self, event):
        """
        Log current positions and pending orders after signal (INFO level)

        Shows:
        - Current inventory with detailed breakdown
        - Position details: entry price, side, unrealized PnL in points per contract
        - Pending orders
        """
        import logging
        logger = logging.getLogger(__name__)

        contract = event.contract

        # Get current position
        position = self.portfolio.get_position(contract)
        market_price = self.portfolio.current_prices.get(contract, Decimal('0'))

        # Update unrealized PnL
        if market_price > 0:
            position.update_unrealized_pnl(market_price)

        # Get pending orders
        active_orders = self.oms.get_active_orders_by_contract(contract)

        # Format position info
        logger.info("=" * 80)
        logger.info(f"📊 POSITION STATUS | {contract}")

        if position.quantity != 0:
            side = "LONG" if position.quantity > 0 else "SHORT"

            # Calculate PnL from the authoritative unrealized_pnl (VND) to ensure consistency
            unrealized_pnl_vnd = position.unrealized_pnl
            # Convert VND to points: divide by CONTRACT_MULTIPLIER (100)
            total_pnl_points = unrealized_pnl_vnd / position.CONTRACT_MULTIPLIER
            # Per-contract average in points
            pnl_points_per_contract = total_pnl_points / abs(position.quantity)

            # Build detailed inventory breakdown showing each contract
            contracts_detail = []
            for _ in range(abs(position.quantity)):
                contracts_detail.append(
                    f"({float(position.average_price):.1f}, {side}, {float(pnl_points_per_contract):+.2f}pts)"
                )

            inventory_detail = f"[{', '.join(contracts_detail)}]"

            logger.info(f"   Inventory ({position.quantity:+d}): {inventory_detail}")
            logger.info(f"   Market Price:         {float(market_price):.1f}")
            logger.info(f"   Total Unrealized PnL: {float(total_pnl_points):+.2f} pts | {float(unrealized_pnl_vnd):+,.0f} (k) VND")
        else:
            logger.info(f"   Inventory:            FLAT (0 contracts)")
            logger.info(f"   Market Price:         {float(market_price):.1f}")

        # Format pending orders info
        if active_orders:
            logger.info(f"📋 PENDING ORDERS ({len(active_orders)}):")
            for order in active_orders:
                logger.info(f"      {order.side.value:4s} {order.quantity} @ {float(order.price):.1f} | {order.status.value}")
        else:
            logger.info(f"📋 PENDING ORDERS:    None")

        logger.info("=" * 80 + "\n")

    def _log_pnl_status_after_fill(self, event, entry_price_before: Decimal, inv_quantity_before: int,
                                     entry_price_after: Decimal, inv_after: int):
        """
        Log PnL statistics after fill (INFO level)

        Args:
            event: Fill event
            entry_price_before: Entry price before this fill
            inv_quantity_before: Inventory quantity before this fill
            entry_price_after: Entry price after this fill (from portfolio)
            inv_after: Inventory quantity after this fill

        Shows:
        - Fill details
        - Accumulated PnL in points
        - PnL of recent closed position (if closed)
        - Average PnL in points and %
        - Current NAV and portfolio PnL %
        """
        import logging
        logger = logging.getLogger(__name__)

        contract = event.contract
        fill_price = event.fill_price
        fill_qty = event.fill_quantity
        side = event.side

        # Check if position was closed
        position_closed = False
        closed_pnl_points = Decimal('0')
        closed_pnl_pct = Decimal('0')

        # Determine if this fill closed a position
        # BID = buy, ASK = sell
        if side == "BID":
            # Buying - closes short position
            # If we had a short position and now flat
            if inv_quantity_before < 0 and inv_after == 0:
                position_closed = True
                # Calculate PnL: (entry_price - fill_price)
                # For short: profit when sell high, buy low
                closed_pnl_points = entry_price_before - fill_price
                if entry_price_before > 0:
                    closed_pnl_pct = (closed_pnl_points / entry_price_before) * 100
        else:  # ASK = sell
            # Selling - closes long position
            # If we had a long position and now flat
            if inv_quantity_before > 0 and inv_after == 0:
                position_closed = True
                # Calculate PnL: (fill_price - entry_price)
                # For long: profit when buy low, sell high
                closed_pnl_points = fill_price - entry_price_before
                if entry_price_before > 0:
                    closed_pnl_pct = (closed_pnl_points / entry_price_before) * 100

        # Track closed position
        if position_closed:
            self.closed_positions.append({
                'contract': contract,
                'pnl_points': float(closed_pnl_points),
                'pnl_pct': float(closed_pnl_pct),
                'timestamp': event.timestamp
            })
            self.total_realized_pnl_points += closed_pnl_points

            # Calculate averages
            avg_pnl_points = self.total_realized_pnl_points / len(self.closed_positions)
            avg_pnl_pct = sum(p['pnl_pct'] for p in self.closed_positions) / len(self.closed_positions)

            # Get current portfolio metrics
            current_nav = self.portfolio.calculate_nav()
            portfolio_pnl = current_nav - self.initial_capital
            portfolio_pnl_pct = (portfolio_pnl / self.initial_capital) * 100
            total_fees = self.monitor.total_fees

            # Format position before (was holding a position)
            side_before = "LONG" if inv_quantity_before > 0 else "SHORT"
            position_before_detail = f"[({float(entry_price_before):.1f}, {side_before}, {float(closed_pnl_points):+.1f}pts)]"

            # Log detailed PnL status
            logger.info("=" * 80)
            logger.info(f"💰 POSITION CLOSED | {contract}")
            logger.info(f"   Fill:                {side} {fill_qty} @ {float(fill_price):.1f}")
            logger.info(f"   Position Before ({inv_quantity_before:+d}): {position_before_detail}")
            logger.info(f"   Position After (0):      FLAT")
            logger.info(f"   Closed PnL:          {float(closed_pnl_points):+.2f} pts | {float(closed_pnl_pct):+.2f}%")
            logger.info(f"")
            logger.info(f"📈 CUMULATIVE PERFORMANCE:")
            logger.info(f"   Total Realized:      {float(self.total_realized_pnl_points):+.2f} pts")
            logger.info(f"   Closed Trades:       {len(self.closed_positions)}")
            logger.info(f"   Avg PnL/Trade:       {float(avg_pnl_points):+.2f} pts | {float(avg_pnl_pct):+.2f}%")
            logger.info(f"")
            logger.info(f"💼 PORTFOLIO STATUS:")
            logger.info(f"   Current NAV:         {float(current_nav):,.0f} (k) VND")
            logger.info(f"   Portfolio PnL:       {float(portfolio_pnl):+,.0f} (k) VND ({float(portfolio_pnl_pct):+.2f}%) | Total Fee: {float(total_fees):,.0f} (k) VND")
            logger.info("=" * 80 + "\n")
        else:
            # Position opened or modified (not closed) - log basic fill info
            # Get current market price for unrealized PnL calculation
            market_price = self.portfolio.current_prices.get(contract, fill_price)

            # Format position before
            if inv_quantity_before != 0:
                side_before = "LONG" if inv_quantity_before > 0 else "SHORT"
                # Calculate unrealized PnL in points
                if inv_quantity_before > 0:
                    unrealized_before = market_price - entry_price_before
                else:
                    unrealized_before = entry_price_before - market_price

                # Build details for each contract
                contracts_before = []
                for _ in range(abs(inv_quantity_before)):
                    contracts_before.append(f"({float(entry_price_before):.1f}, {side_before}, {float(unrealized_before):+.1f}pts)")
                position_before_detail = f"[{', '.join(contracts_before)}]"
            else:
                position_before_detail = "FLAT"

            # Format position after
            if inv_after != 0:
                side_after = "LONG" if inv_after > 0 else "SHORT"
                # Entry price after
                if inv_quantity_before == 0:
                    # Just opened, entry is fill price
                    entry_after = fill_price
                else:
                    # Modified existing position
                    entry_after = entry_price_after

                # Calculate unrealized PnL in points
                if inv_after > 0:
                    unrealized_after = market_price - entry_after
                else:
                    unrealized_after = entry_after - market_price

                # Build details for each contract
                contracts_after = []
                for _ in range(abs(inv_after)):
                    contracts_after.append(f"({float(entry_after):.1f}, {side_after}, {float(unrealized_after):+.1f}pts)")
                position_after_detail = f"[{', '.join(contracts_after)}]"
            else:
                position_after_detail = "FLAT"

            # Get current portfolio metrics
            current_nav = self.portfolio.calculate_nav()
            portfolio_pnl = current_nav - self.initial_capital
            portfolio_pnl_pct = (portfolio_pnl / self.initial_capital) * 100
            total_fees = self.monitor.total_fees

            logger.info("=" * 80)
            logger.info(f"📝 FILL EXECUTED | {contract}")
            logger.info(f"   Fill:                {side} {fill_qty} @ {float(fill_price):.1f}")
            logger.info(f"   Position Before ({inv_quantity_before:+d}): {position_before_detail}")
            logger.info(f"   Position After ({inv_after:+d}):  {position_after_detail}")

            logger.info(f"")
            logger.info(f"💼 PORTFOLIO STATUS:")
            logger.info(f"   Current NAV:         {float(current_nav):,.0f} (k) VND")
            logger.info(f"   Portfolio PnL:       {float(portfolio_pnl):+,.0f} (k) VND ({float(portfolio_pnl_pct):+.2f}%) | Total Fee: {float(total_fees):,.0f} (k) VND")
            logger.info("=" * 80 + "\n")

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

        # Disconnect from PaperBroker if connected
        if self.execution_mode == 'paperbroker' and self.connector:
            print("Disconnecting from PaperBroker...")
            self.connector.disconnect()

        # Shutdown execution engine
        if hasattr(self.execution, 'shutdown'):
            self.execution.shutdown()

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

                    # Periodic status logging every 30 seconds (~3000 iterations at 10ms)
                    self.event_count += 1
                    if self.event_count % 3000 == 0:
                        self._log_status()
            else:
                print("Running indefinitely (Ctrl+C to stop)...")
                while self._running:
                    # Process queued events to dispatch to handlers
                    self.event_bus.process_events()
                    time.sleep(0.01)  # 10ms processing interval

                    # Periodic status logging every 30 seconds (~3000 iterations at 10ms)
                    self.event_count += 1
                    if self.event_count % 3000 == 0:
                        self._log_status()
        except KeyboardInterrupt:
            pass

        # Stop and generate results
        if self._running:
            return self.stop()
        else:
            return None

    def _log_status(self):
        """Log periodic status update with key metrics"""
        try:
            active_orders = len(self.oms.get_active_orders())
            pending_count = 0

            # Get pending count from execution engine if available
            if hasattr(self.execution, 'get_pending_count'):
                pending_count = self.execution.get_pending_count()
            elif hasattr(self.execution, 'pending_orders'):
                pending_count = len(self.execution.pending_orders)

            position_count = len(self.portfolio.positions)
            current_nav = float(self.portfolio.calculate_nav())

            import logging
            logger = logging.getLogger('paper_trading.engine')
            logger.info(
                f"📊 Status: events={self.event_count} | "
                f"active_orders={active_orders} | "
                f"pending={pending_count} | "
                f"positions={position_count} | "
                f"nav={current_nav:,.2f}"
            )
        except Exception as e:
            # Don't let logging errors crash the main loop
            import logging
            logger = logging.getLogger('paper_trading.engine')
            logger.debug(f"Error logging status: {e}")

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

        # Calculate HPR manually if not provided by PLUTUS
        final_nav = self.portfolio.calculate_nav()
        if 'hpr' not in plutus_metrics or plutus_metrics.get('hpr') == 0.0:
            # HPR = (final_nav - initial_capital) / initial_capital
            hpr = float((final_nav - self.initial_capital) / self.initial_capital)
        else:
            hpr = plutus_metrics.get('hpr', 0.0)

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
            hpr=hpr,

            # Trading statistics (from Monitor)
            total_trades=self.monitor.total_trades,
            buy_trades=self.monitor.buy_count if hasattr(self.monitor, 'buy_count') else 0,
            sell_trades=self.monitor.sell_count if hasattr(self.monitor, 'sell_count') else 0,
            total_fees=self.monitor.get_total_fees() if hasattr(self.monitor, 'get_total_fees') else Decimal('0'),

            # Portfolio timeline (from Portfolio)
            initial_capital=self.initial_capital,
            final_nav=final_nav,
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

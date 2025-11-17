"""
Redis Market Data Handler

Subscribes to Redis Pub/Sub channels and publishes MarketDataEvents.
"""
import redis
import json
import threading
import time
from decimal import Decimal
from datetime import datetime, date
from dateutil.rrule import rrule, MONTHLY, TH
from typing import List, Optional, Callable, Literal
import logging

from core.event import EventBus, MarketDataEvent
from core.enums import EventType


class RedisMarketDataHandler:
    """
    Redis Pub/Sub market data handler

    Responsibilities:
    - Subscribe to Redis channels for market data
    - Listen for incoming messages
    - Deserialize JSON to MarketDataEvent
    - Publish events to EventBus
    - Handle reconnection on disconnect

    Example:
        handler = RedisMarketDataHandler(
            event_bus=bus,
            redis_host='localhost',
            redis_port=6379
        )
        handler.subscribe(['VN30F1M', 'VN30F2M'])
        handler.start()
    """

    def __init__(
        self,
        event_bus: EventBus,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        redis_decode_responses: bool = True,
        channel_prefix: str = 'market',
        mode: Literal['playback', 'live'] = 'playback',
        f2m_window_days: int = 3
    ):
        """
        Initialize Redis handler

        Args:
            event_bus: EventBus for publishing market data events
            redis_host: Redis server hostname
            redis_port: Redis server port
            redis_db: Redis database number
            redis_password: Redis password for authentication (None if no auth required)
            redis_decode_responses: Whether to decode responses to strings (True) or keep as bytes (False)
            channel_prefix: Channel name prefix (e.g., 'market:VN30F1M')
            mode: Operating mode - 'playback' (abstract symbols) or 'live' (actual contracts)
            f2m_window_days: Days before expiration to subscribe to F2M (default: 3)
        """
        self.event_bus = event_bus
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password
        self.redis_decode_responses = redis_decode_responses
        self.channel_prefix = channel_prefix
        self.mode = mode
        self.f2m_window_days = f2m_window_days

        # Redis client and pubsub
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

        # Thread management
        self.listener_thread: Optional[threading.Thread] = None
        self.running = False

        # Subscribed contracts (for reconnection)
        self.subscribed_contracts: List[str] = []
        self.f2m_subscribed = False  # Track F2M subscription state
        self.f1m_contract: Optional[str] = None  # Current F1M contract symbol
        self.f2m_contract: Optional[str] = None  # Current F2M contract symbol
        self.last_f1_contract: Optional[str] = None  # Previous F1 contract for rollover detection

        # Statistics
        self.messages_received = 0
        self.messages_processed = 0
        self.messages_failed = 0
        self.reconnect_count = 0
        self.last_message_time: Optional[datetime] = None

        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """
        Connect to Redis server

        Returns:
            True if connected successfully
        """
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=self.redis_decode_responses,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30
            )

            # Test connection
            self.redis_client.ping()

            self.pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
            self.logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            return True

        except redis.ConnectionError as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to Redis: {e}")
            return False

    def subscribe(self, contracts: List[str]):
        """
        Subscribe to market data channels

        In playback mode: Subscribe only to F1M initially (abstract symbol VN30F1M)
        In live mode: Subscribe to resolved F1M contract (e.g., VN30F2510)

        F2M subscription is conditional and happens dynamically during rollover period.

        Args:
            contracts: List of contract symbols (e.g., ['VN30F1M'] or ['VN30F2510'])
        """
        if not self.pubsub:
            self.logger.error("Not connected to Redis. Call connect() first.")
            return

        # Store contracts for reconnection
        self.subscribed_contracts = contracts

        # Initially subscribe only to F1M
        # F2M will be subscribed conditionally during rollover
        f1m_contracts = [c for c in contracts if 'F1M' in c or (self.mode == 'live' and c not in [self.f2m_contract])]

        if f1m_contracts:
            self.f1m_contract = f1m_contracts[0]
            channels = [f"{self.channel_prefix}:{contract}" for contract in f1m_contracts]
            self.pubsub.subscribe(*channels)
            self.logger.info(f"Subscribed to F1M channel: {channels}")

        # Check if F2M is explicitly provided (for backward compatibility)
        f2m_contracts = [c for c in contracts if 'F2M' in c]
        if f2m_contracts:
            self.f2m_contract = f2m_contracts[0]
            self.subscribe_to_f2m()

    def subscribe_to_f2m(self):
        """Subscribe to F2M channel during rollover period"""
        if not self.pubsub:
            self.logger.error("Not connected to Redis. Call connect() first.")
            return

        if self.f2m_subscribed:
            self.logger.debug("Already subscribed to F2M")
            return

        if not self.f2m_contract:
            # Infer F2M contract from F1M
            if self.f1m_contract:
                self.f2m_contract = self.f1m_contract.replace('F1M', 'F2M')
            else:
                self.logger.error("Cannot subscribe to F2M: no F1M contract set")
                return

        channel = f"{self.channel_prefix}:{self.f2m_contract}"
        self.pubsub.subscribe(channel)
        self.f2m_subscribed = True
        self.logger.info(f"Subscribed to F2M channel: {channel}")

    def unsubscribe_from_f2m(self):
        """Unsubscribe from F2M channel after rollover period"""
        if not self.pubsub:
            return

        if not self.f2m_subscribed:
            self.logger.debug("Not subscribed to F2M, nothing to unsubscribe")
            return

        if self.f2m_contract:
            channel = f"{self.channel_prefix}:{self.f2m_contract}"
            self.pubsub.unsubscribe(channel)
            self.f2m_subscribed = False
            self.logger.info(f"Unsubscribed from F2M channel: {channel}")

    def _calculate_third_thursday(self, year: int, month: int) -> date:
        """
        Calculate the third Thursday of a given month (VN30 futures expiration date)

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            Date of third Thursday
        """
        # Generate first 3 Thursdays starting from the month
        start_date = date(year, month, 1)

        # Get first 3 Thursdays (third Thursday is index 2)
        thursdays = list(rrule(MONTHLY, byweekday=TH, dtstart=start_date, count=3))

        if len(thursdays) >= 3:
            return thursdays[2].date()
        else:
            # Fallback: should not happen
            self.logger.warning(f"Could not find third Thursday for {year}-{month}")
            return start_date

    def _detect_rollover_from_contract(self, current_contract: str, previous_contract: Optional[str]) -> bool:
        """
        Detect rollover by comparing contract codes (e.g., VN30F2201 -> VN30F2202)

        Args:
            current_contract: Current contract symbol
            previous_contract: Previous contract symbol

        Returns:
            True if contract code changed (indicating rollover)
        """
        if previous_contract is None:
            return False

        # Extract month code from contract (e.g., VN30F2201 -> 2201)
        # Assumes contract format: VN30F[YYMM]
        try:
            current_month = current_contract[-4:]
            previous_month = previous_contract[-4:]

            if current_month != previous_month:
                self.logger.info(f"Rollover detected: {previous_contract} -> {current_contract}")
                return True
        except (IndexError, ValueError) as e:
            self.logger.warning(f"Error parsing contract codes: {e}")

        return False

    def _is_near_expiration(self, current_date: date, current_contract: str) -> bool:
        """
        Check if current date is within N days before expiration

        Args:
            current_date: Current date
            current_contract: Current contract symbol (e.g., VN30F2201)

        Returns:
            True if within rollover window
        """
        try:
            # Extract year/month from contract (e.g., VN30F2201 -> 22, 01)
            month_code = current_contract[-4:]
            year = 2000 + int(month_code[:2])
            month = int(month_code[2:])

            # Calculate expiration date (third Thursday)
            expiration = self._calculate_third_thursday(year, month)

            # Check if within window
            days_to_expiration = (expiration - current_date).days

            if 0 <= days_to_expiration <= self.f2m_window_days:
                return True

        except (ValueError, IndexError) as e:
            self.logger.warning(f"Error calculating expiration for {current_contract}: {e}")

        return False

    def _should_subscribe_f2m(
        self,
        current_date: date,
        current_contract: str,
        previous_contract: Optional[str] = None
    ) -> bool:
        """
        Combined logic to determine if F2M should be subscribed

        Uses both contract code change detection and timestamp-based window check

        Args:
            current_date: Current date
            current_contract: Current contract symbol
            previous_contract: Previous contract symbol (None if first message)

        Returns:
            True if F2M should be subscribed
        """
        # Method 1: Detect rollover from contract code change
        if previous_contract and self._detect_rollover_from_contract(current_contract, previous_contract):
            return True

        # Method 2: Check if within expiration window
        if self._is_near_expiration(current_date, current_contract):
            return True

        return False

    def check_and_manage_f2m_subscription(self, current_date: date, current_contract: str):
        """
        Check if F2M subscription should be activated/deactivated

        Call this method periodically or on each F1M message to manage F2M subscription

        Args:
            current_date: Current date from F1M message
            current_contract: Current F1M contract symbol
        """
        should_subscribe = self._should_subscribe_f2m(
            current_date,
            current_contract,
            self.last_f1_contract
        )

        if should_subscribe and not self.f2m_subscribed:
            self.subscribe_to_f2m()
        elif not should_subscribe and self.f2m_subscribed:
            self.unsubscribe_from_f2m()

        # Update last contract for next check
        self.last_f1_contract = current_contract

    def start(self):
        """Start listening for messages in background thread"""
        if self.running:
            self.logger.warning("Handler already running")
            return

        if not self.pubsub:
            self.logger.error("Not connected to Redis. Call connect() and subscribe() first.")
            return

        self.running = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()

        self.logger.info("Redis listener started")

    def stop(self):
        """
        Stop listening and disconnect

        Properly interrupts the blocking listen() iterator by closing pubsub first.
        """
        self.logger.info("Stopping Redis listener...")
        self.running = False

        # Close pubsub first to interrupt blocking listen() call
        if self.pubsub:
            try:
                self.pubsub.close()
                self.logger.debug("PubSub closed")
            except Exception as e:
                self.logger.error(f"Error closing pubsub: {e}")

        # Wait for listener thread to finish
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=5)
            if self.listener_thread.is_alive():
                self.logger.warning("Listener thread did not stop within timeout")

        # Close Redis client
        if self.redis_client:
            try:
                self.redis_client.close()
                self.logger.debug("Redis client closed")
            except Exception as e:
                self.logger.error(f"Error closing Redis client: {e}")

        self.logger.info("Redis listener stopped")

    def _listen_loop(self):
        """
        Main listening loop (runs in background thread)

        Uses blocking iterator pattern (listen()) instead of polling (get_message())
        for better performance and reliability.
        """
        self.logger.info("Starting listen loop...")

        try:
            # Use blocking iterator - more efficient than polling with get_message()
            # listen() blocks until a message arrives, eliminating race conditions
            for message in self.pubsub.listen():
                # Check if we should stop
                if not self.running:
                    break

                # Process actual messages (ignore subscribe confirmations)
                if message and message['type'] == 'message':
                    self.messages_received += 1
                    self.last_message_time = datetime.now()
                    self._process_message(message)

        except redis.ConnectionError as e:
            # Connection closed - check if this is expected shutdown
            if self.running:
                self.logger.error(f"Redis connection lost: {e}")
                self._handle_reconnect()
            else:
                self.logger.debug("Connection closed during shutdown (expected)")

        except (ValueError, OSError) as e:
            # I/O operation on closed file - happens during shutdown when pubsub is closed
            if self.running:
                self.logger.error(f"I/O error in listen loop: {e}")
            else:
                self.logger.debug("Pubsub closed during shutdown (expected)")

        except Exception as e:
            # Unexpected error
            self.logger.error(f"Unexpected error in listen loop: {e}", exc_info=True)

        self.logger.info("Listen loop ended")

    def _process_message(self, message: dict):
        """
        Process incoming Redis message

        Args:
            message: Redis message dict with 'data' field
        """
        try:
            # Deserialize JSON
            data = json.loads(message['data'])
            self.logger.debug(f"📥 Received message fields: {list(data.keys())}")
            self.logger.debug(f"📥 Full message data: {data}")

            # Validate required fields
            required_fields = ['timestamp', 'instrument', 'latest_matched_price', 'bid_price_1', 'ask_price_1']
            for field in required_fields:
                if field not in data:
                    raise KeyError(f"Missing required field: {field}")

            # Preprocess the data
            contract = data['instrument'].split(':')[1]
            price = data['latest_matched_price']
            if not price:
                return
            else:
                price=Decimal(str(price))

            # Create MarketDataEvent
            event = MarketDataEvent(
                timestamp=datetime.fromtimestamp(data['timestamp']),
                # contract=data['contract'],
                contract=contract,
                price=Decimal(str(data['latest_matched_price'])),
                bid=Decimal(str(data['bid_price_1'])),
                ask=Decimal(str(data['ask_price_1'])),
                spread=Decimal(str(data.get('spread', float(data['ask_price_1']) - float(data['bid_price_1']))))
            )

            # Check and manage F2M subscription on F1M messages
            # This enables automatic F2M subscription during rollover period
            if 'F1M' in contract or (self.f1m_contract and contract == self.f1m_contract):
                # Extract actual contract symbol from message (e.g., VN30F2201 from tickersymbol field if available)
                # In playback mode, contract is abstract (VN30F1M), but we need actual contract for rollover detection
                # The actual contract symbol should be passed in a separate field or extracted from context

                # For now, we'll use the timestamp to derive the date for rollover detection
                current_date = event.timestamp.date()

                # Try to get actual contract from message data (if available)
                actual_contract = data.get('tickersymbol', contract)

                # Only manage F2M subscription if we have an actual contract code (not abstract VN30F1M)
                if len(actual_contract) > 8:  # VN30F2201 has more characters than VN30F1M
                    self.check_and_manage_f2m_subscription(current_date, actual_contract)

            # Publish to EventBus
            self.event_bus.publish(event)

            self.messages_processed += 1

            # Log every 100 messages
            if self.messages_processed % 100 == 0:
                self.logger.info(f"Processed {self.messages_processed} messages")

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            self.messages_failed += 1
            self.logger.error(f"Failed to process message: {e}")
            self.logger.debug(f"Message data: {message.get('data', 'N/A')}")

    def _handle_reconnect(self):
        """Handle reconnection after disconnect"""
        self.reconnect_count += 1
        self.logger.info(f"Attempting reconnection (attempt {self.reconnect_count})...")

        # Wait before reconnecting
        time.sleep(2)

        # Try to reconnect
        if self.connect():
            self.logger.info("Reconnected successfully")

            # Resubscribe to channels
            if self.subscribed_contracts:
                self.subscribe(self.subscribed_contracts)
                self.logger.info(f"Resubscribed to {len(self.subscribed_contracts)} contracts")
            else:
                self.logger.warning("No contracts to resubscribe to")
        else:
            self.logger.error("Reconnection failed, will retry...")

    def get_statistics(self) -> dict:
        """
        Get handler statistics

        Returns:
            Dictionary with statistics
        """
        return {
            'messages_received': self.messages_received,
            'messages_processed': self.messages_processed,
            'messages_failed': self.messages_failed,
            'processing_errors': self.messages_failed,  # Alias for compatibility
            'reconnect_count': self.reconnect_count,
            'is_running': self.running,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None
        }

    def get_latency_ms(self) -> Optional[float]:
        """
        Calculate approximate latency in milliseconds

        Returns:
            Latency in ms, or None if no messages received
        """
        if not self.last_message_time:
            return None

        latency = (datetime.now() - self.last_message_time).total_seconds() * 1000
        return latency

    def is_healthy(self) -> bool:
        """
        Check if handler is healthy

        Returns:
            True if running and received message in last 60 seconds
        """
        if not self.running:
            return False

        if not self.last_message_time:
            # No messages yet, but might be starting up
            return True

        # Check if we've received a message in the last 60 seconds
        time_since_last = (datetime.now() - self.last_message_time).total_seconds()
        return time_since_last < 60

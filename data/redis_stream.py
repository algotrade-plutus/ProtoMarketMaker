"""
Redis Market Data Handler

Subscribes to Redis Pub/Sub channels and publishes MarketDataEvents.
"""
import redis
import json
import threading
import time
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Callable
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
        channel_prefix: str = 'market'
    ):
        """
        Initialize Redis handler

        Args:
            event_bus: EventBus for publishing market data events
            redis_host: Redis server hostname
            redis_port: Redis server port
            redis_db: Redis database number
            channel_prefix: Channel name prefix (e.g., 'market:VN30F1M')
        """
        self.event_bus = event_bus
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.channel_prefix = channel_prefix

        # Redis client and pubsub
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

        # Thread management
        self.listener_thread: Optional[threading.Thread] = None
        self.running = False

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
                decode_responses=True,
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

        Args:
            contracts: List of contract symbols (e.g., ['VN30F1M', 'VN30F2M'])
        """
        if not self.pubsub:
            self.logger.error("Not connected to Redis. Call connect() first.")
            return

        channels = [f"{self.channel_prefix}:{contract}" for contract in contracts]
        self.pubsub.subscribe(*channels)

        self.logger.info(f"Subscribed to channels: {channels}")

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
        """Stop listening and disconnect"""
        self.logger.info("Stopping Redis listener...")
        self.running = False

        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=5)

        if self.pubsub:
            try:
                self.pubsub.close()
            except Exception as e:
                self.logger.error(f"Error closing pubsub: {e}")

        if self.redis_client:
            try:
                self.redis_client.close()
            except Exception as e:
                self.logger.error(f"Error closing Redis client: {e}")

        self.logger.info("Redis listener stopped")

    def _listen_loop(self):
        """Main listening loop (runs in background thread)"""
        self.logger.info("Starting listen loop...")

        while self.running:
            try:
                # Get message with timeout
                message = self.pubsub.get_message(timeout=1.0)

                if message and message['type'] == 'message':
                    self.messages_received += 1
                    self.last_message_time = datetime.now()
                    self._process_message(message)

            except redis.ConnectionError as e:
                self.logger.error(f"Redis connection lost: {e}")
                self._handle_reconnect()

            except Exception as e:
                self.logger.error(f"Error in listen loop: {e}", exc_info=True)
                time.sleep(1)

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

            # Validate required fields
            required_fields = ['timestamp', 'contract', 'price', 'bid', 'ask']
            for field in required_fields:
                if field not in data:
                    raise KeyError(f"Missing required field: {field}")

            # Create MarketDataEvent
            event = MarketDataEvent(
                timestamp=datetime.fromisoformat(data['timestamp']),
                contract=data['contract'],
                price=Decimal(str(data['price'])),
                bid=Decimal(str(data['bid'])),
                ask=Decimal(str(data['ask'])),
                spread=Decimal(str(data.get('spread', float(data['ask']) - float(data['bid']))))
            )

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
            # Resubscribe to channels (would need to store original contracts)
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

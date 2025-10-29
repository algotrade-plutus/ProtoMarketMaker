"""
Redis Market Data Publisher

Publishes simulated market data to Redis for testing.
"""
import redis
import json
import time
import argparse
from decimal import Decimal
from datetime import datetime
import pandas as pd
from typing import Optional
import logging


class RedisMarketDataPublisher:
    """
    Publishes market data to Redis Pub/Sub

    Simulates live market data feed by:
    - Loading historical CSV data
    - Publishing to Redis at specified rate
    - Supporting multiple contracts

    Example:
        publisher = RedisMarketDataPublisher(
            redis_host='localhost',
            redis_port=6379
        )
        publisher.publish_from_csv(
            'data/historical.csv',
            rate_hz=10  # 10 messages per second
        )
    """

    def __init__(
        self,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        channel_prefix: str = 'market'
    ):
        """
        Initialize publisher

        Args:
            redis_host: Redis server hostname
            redis_port: Redis server port
            channel_prefix: Channel prefix
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.channel_prefix = channel_prefix

        self.redis_client: Optional[redis.Redis] = None
        self.logger = logging.getLogger(__name__)
        self.messages_published = 0

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
                decode_responses=True,
                socket_connect_timeout=5
            )

            # Test connection
            self.redis_client.ping()
            self.logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            return True

        except redis.ConnectionError as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            return False

    def publish_message(self, contract: str, data: dict):
        """
        Publish single message to Redis

        Args:
            contract: Contract symbol
            data: Market data dictionary
        """
        if not self.redis_client:
            raise RuntimeError("Not connected to Redis. Call connect() first.")

        channel = f"{self.channel_prefix}:{contract}"
        message = json.dumps(data)

        self.redis_client.publish(channel, message)
        self.messages_published += 1

    def publish_from_csv(
        self,
        csv_path: str,
        rate_hz: float = 1.0,
        loop: bool = False,
        max_messages: Optional[int] = None
    ):
        """
        Publish market data from CSV file

        Args:
            csv_path: Path to CSV file
            rate_hz: Publishing rate (messages per second)
            loop: Whether to loop continuously
            max_messages: Maximum number of messages to publish (None = unlimited)
        """
        # Load data
        data = pd.read_csv(csv_path)
        data['datetime'] = pd.to_datetime(data['datetime'])

        self.logger.info(f"Loaded {len(data)} rows from {csv_path}")
        self.logger.info(f"Publishing at {rate_hz} Hz")

        sleep_time = 1.0 / rate_hz
        messages_sent = 0

        try:
            while True:
                for index, row in data.iterrows():
                    # Create message
                    message_data = {
                        'timestamp': row['datetime'].isoformat(),
                        'contract': row['tickersymbol'],
                        'price': float(row['price']),
                        'bid': float(row['best-bid']),
                        'ask': float(row['best-ask']),
                        'spread': float(row['spread'])
                    }

                    # Publish
                    self.publish_message(row['tickersymbol'], message_data)
                    messages_sent += 1

                    # Log progress
                    if messages_sent % 100 == 0:
                        self.logger.info(f"Published {messages_sent} messages")

                    # Check max messages
                    if max_messages and messages_sent >= max_messages:
                        self.logger.info(f"Reached max messages: {max_messages}")
                        return

                    # Rate limiting
                    time.sleep(sleep_time)

                if not loop:
                    break

                self.logger.info("Looping back to start...")

        except KeyboardInterrupt:
            self.logger.info("Publishing stopped by user")

        finally:
            self.logger.info(f"Total messages published: {self.messages_published}")

    def publish_random_data(
        self,
        contracts: list[str],
        base_price: float = 1250.0,
        rate_hz: float = 1.0,
        duration_seconds: Optional[int] = None,
        volatility: float = 0.5
    ):
        """
        Publish random market data for testing

        Args:
            contracts: List of contract symbols
            base_price: Base price for random walk
            rate_hz: Publishing rate
            duration_seconds: Duration in seconds (None = infinite)
            volatility: Price volatility (standard deviation of changes)
        """
        import random

        prices = {contract: base_price for contract in contracts}
        start_time = time.time()

        self.logger.info(f"Publishing random data for {contracts}")
        self.logger.info(f"Rate: {rate_hz} Hz, Duration: {duration_seconds}s")

        try:
            while True:
                for contract in contracts:
                    # Random walk with normal distribution
                    change = random.gauss(0, volatility)
                    prices[contract] += change

                    # Keep price positive
                    prices[contract] = max(prices[contract], 1.0)

                    # Create message
                    price = round(prices[contract], 1)
                    message_data = {
                        'timestamp': datetime.now().isoformat(),
                        'contract': contract,
                        'price': price,
                        'bid': round(price - 1, 1),
                        'ask': round(price + 1, 1),
                        'spread': 2.0
                    }

                    self.publish_message(contract, message_data)

                    # Rate limiting per contract
                    time.sleep(1.0 / (rate_hz * len(contracts)))

                # Check duration
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    self.logger.info(f"Reached duration: {duration_seconds}s")
                    break

        except KeyboardInterrupt:
            self.logger.info("Publishing stopped by user")

        finally:
            self.logger.info(f"Total messages published: {self.messages_published}")

    def publish_sine_wave(
        self,
        contracts: list[str],
        base_price: float = 1250.0,
        amplitude: float = 10.0,
        period_seconds: float = 60.0,
        rate_hz: float = 1.0,
        duration_seconds: Optional[int] = None
    ):
        """
        Publish sine wave price data for testing

        Args:
            contracts: List of contract symbols
            base_price: Base price (midpoint)
            amplitude: Wave amplitude
            period_seconds: Wave period in seconds
            rate_hz: Publishing rate
            duration_seconds: Duration in seconds (None = infinite)
        """
        import math

        start_time = time.time()

        self.logger.info(f"Publishing sine wave data for {contracts}")
        self.logger.info(f"Base: {base_price}, Amplitude: {amplitude}, Period: {period_seconds}s")

        try:
            while True:
                elapsed = time.time() - start_time

                for contract in contracts:
                    # Calculate sine wave price
                    angle = 2 * math.pi * elapsed / period_seconds
                    price = base_price + amplitude * math.sin(angle)
                    price = round(price, 1)

                    # Create message
                    message_data = {
                        'timestamp': datetime.now().isoformat(),
                        'contract': contract,
                        'price': price,
                        'bid': round(price - 1, 1),
                        'ask': round(price + 1, 1),
                        'spread': 2.0
                    }

                    self.publish_message(contract, message_data)

                    time.sleep(1.0 / (rate_hz * len(contracts)))

                # Check duration
                if duration_seconds and elapsed >= duration_seconds:
                    self.logger.info(f"Reached duration: {duration_seconds}s")
                    break

        except KeyboardInterrupt:
            self.logger.info("Publishing stopped by user")

        finally:
            self.logger.info(f"Total messages published: {self.messages_published}")

    def get_statistics(self) -> dict:
        """Get publisher statistics"""
        return {
            'messages_published': self.messages_published,
            'connected': self.redis_client is not None
        }


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Redis Market Data Publisher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Publish from CSV at 10 Hz
  python -m tools.redis_publisher --csv data/historical.csv --rate 10

  # Generate random data for testing
  python -m tools.redis_publisher --random --contracts VN30F1M VN30F2M --rate 5

  # Publish sine wave data
  python -m tools.redis_publisher --sine --contracts VN30F1M --rate 1 --duration 60
        """
    )

    parser.add_argument('--host', default='localhost', help='Redis host')
    parser.add_argument('--port', type=int, default=6379, help='Redis port')
    parser.add_argument('--csv', help='CSV file to publish')
    parser.add_argument('--rate', type=float, default=1.0, help='Messages per second')
    parser.add_argument('--loop', action='store_true', help='Loop continuously')
    parser.add_argument('--max-messages', type=int, help='Maximum messages to publish')
    parser.add_argument('--random', action='store_true', help='Generate random data')
    parser.add_argument('--sine', action='store_true', help='Generate sine wave data')
    parser.add_argument('--contracts', nargs='+', default=['VN30F1M'], help='Contracts')
    parser.add_argument('--duration', type=int, help='Duration in seconds')
    parser.add_argument('--base-price', type=float, default=1250.0, help='Base price')
    parser.add_argument('--volatility', type=float, default=0.5, help='Price volatility')
    parser.add_argument('--amplitude', type=float, default=10.0, help='Sine wave amplitude')
    parser.add_argument('--period', type=float, default=60.0, help='Sine wave period (seconds)')
    parser.add_argument('--log-level', default='INFO', help='Logging level')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create publisher
    publisher = RedisMarketDataPublisher(
        redis_host=args.host,
        redis_port=args.port
    )

    # Connect to Redis
    if not publisher.connect():
        print(f"Error: Could not connect to Redis at {args.host}:{args.port}")
        print("Make sure Redis server is running:")
        print("  docker run -d -p 6379:6379 redis:latest")
        return 1

    # Publish data
    try:
        if args.sine:
            publisher.publish_sine_wave(
                contracts=args.contracts,
                base_price=args.base_price,
                amplitude=args.amplitude,
                period_seconds=args.period,
                rate_hz=args.rate,
                duration_seconds=args.duration
            )
        elif args.random:
            publisher.publish_random_data(
                contracts=args.contracts,
                base_price=args.base_price,
                rate_hz=args.rate,
                duration_seconds=args.duration,
                volatility=args.volatility
            )
        elif args.csv:
            publisher.publish_from_csv(
                csv_path=args.csv,
                rate_hz=args.rate,
                loop=args.loop,
                max_messages=args.max_messages
            )
        else:
            print("Error: Must specify --csv, --random, or --sine")
            return 1

    except Exception as e:
        logging.error(f"Error during publishing: {e}", exc_info=True)
        return 1

    return 0


if __name__ == '__main__':
    exit(main())

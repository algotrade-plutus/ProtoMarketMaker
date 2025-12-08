"""
Redis Market Data Publisher

Publishes simulated market data to Redis for testing.
"""
import redis
import json
import time
import argparse
from decimal import Decimal
from datetime import datetime, date
from dateutil.rrule import rrule, MONTHLY, TH
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
        channel_prefix: str = 'market',
        normalize_contracts: bool = False
    ):
        """
        Initialize publisher

        Args:
            redis_host: Redis server hostname
            redis_port: Redis server port
            channel_prefix: Channel prefix
            normalize_contracts: If True, convert actual contract codes (VN30F2202)
                               to abstract symbols (VN30F1M) for playback mode
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.channel_prefix = channel_prefix
        self.normalize_contracts = normalize_contracts

        self.redis_pool: Optional[redis.ConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.logger = logging.getLogger(__name__)
        self.messages_published = 0

        # Track current front-month contract for normalization
        self._current_f1m_contract: Optional[str] = None

    def connect(self) -> bool:
        """
        Connect to Redis server using connection pool (thread-safe)

        Returns:
            True if connected successfully
        """
        try:
            # Use connection pool for thread-safe access
            self.redis_pool = redis.ConnectionPool(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis_client = redis.Redis(connection_pool=self.redis_pool)

            # Test connection
            self.redis_client.ping()
            self.logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            return True

        except redis.ConnectionError as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            return False

    def disconnect(self):
        """
        Disconnect from Redis server
        """
        if self.redis_client:
            try:
                self.redis_client.close()
                self.logger.info("Disconnected from Redis")
            except Exception as e:
                self.logger.error(f"Error disconnecting from Redis: {e}")
            finally:
                self.redis_client = None
        if self.redis_pool:
            try:
                self.redis_pool.disconnect()
            except Exception:
                pass
            finally:
                self.redis_pool = None

    def _normalize_contract(self, contract: str) -> str:
        """
        Normalize actual contract code to abstract symbol

        For merged CSV data in playback mode, the tickersymbol column contains
        actual contract codes (e.g., VN30F2202) but we want to publish to
        abstract channels (VN30F1M, VN30F2M).

        In merged data, all rows represent F1M data (the front-month contract).
        When a rollover happens, the tickersymbol changes (e.g., VN30F2202 → VN30F2203)
        but it's still F1M data.

        Args:
            contract: Actual contract code (e.g., 'VN30F2202')

        Returns:
            Abstract symbol ('VN30F1M' for all contracts in merged data)
        """
        if not self.normalize_contracts:
            return contract

        # For merged CSV data, all data is F1M
        # The contract code changes at rollovers but it's still the front month
        # VN30F2202 = 9 chars, VN30F1M = 7 chars
        if contract.startswith('VN30F') and len(contract) == 9:
            # Actual contract code like VN30F2202
            return 'VN30F1M'

        # Already an abstract symbol
        return contract

    def load_csv(self, csv_path: str):
        """
        Load CSV file into memory for later publishing

        Args:
            csv_path: Path to CSV file

        Returns:
            DataFrame with loaded data
        """
        self.data = pd.read_csv(csv_path)
        self.data['datetime'] = pd.to_datetime(self.data['datetime'])
        self.logger.info(f"Loaded {len(self.data)} rows from {csv_path}")
        return self.data

    def load_separate_files(self, f1m_csv: str, f2m_csv: str, f2m_window_days: int = 3):
        """
        Load separate F1M and F2M CSV files for dual-file publishing

        Args:
            f1m_csv: Path to F1M CSV file
            f2m_csv: Path to F2M CSV file
            f2m_window_days: Days before expiration to start publishing F2M (default: 3)

        Returns:
            Tuple of (f1m_data, f2m_data) DataFrames
        """
        # Load F1M data
        f1m_data = pd.read_csv(f1m_csv)
        f1m_data['datetime'] = pd.to_datetime(f1m_data['datetime'])
        self.logger.info(f"Loaded {len(f1m_data)} F1M rows from {f1m_csv}")

        # Load F2M data
        f2m_data = pd.read_csv(f2m_csv)
        f2m_data['datetime'] = pd.to_datetime(f2m_data['datetime'])
        self.logger.info(f"Loaded {len(f2m_data)} F2M rows from {f2m_csv}")

        # Store for later use
        self.f1m_data = f1m_data
        self.f2m_data = f2m_data
        self.f2m_window_days = f2m_window_days

        return f1m_data, f2m_data

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

    def _detect_rollover_from_contract(self, current_contract: str, previous_contract: str) -> bool:
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

    def _should_publish_f2m(
        self,
        current_date: date,
        current_contract: str,
        previous_contract: Optional[str] = None
    ) -> bool:
        """
        Combined logic to determine if F2M should be published

        Uses both contract code change detection and timestamp-based window check

        Args:
            current_date: Current date
            current_contract: Current contract symbol
            previous_contract: Previous contract symbol (None if first row)

        Returns:
            True if F2M should be published
        """
        # Method 1: Detect rollover from contract code change
        if previous_contract and self._detect_rollover_from_contract(current_contract, previous_contract):
            return True

        # Method 2: Check if within expiration window
        if self._is_near_expiration(current_date, current_contract):
            return True

        return False

    def _publish_row(self, row: pd.Series, contract_symbol: str):
        """
        Extract common logic for publishing a single row

        Args:
            row: DataFrame row with market data
            contract_symbol: Contract symbol to use (VN30F1M or VN30F2M)
        """
        message_data = {
            'timestamp': row['datetime'].isoformat(),
            'contract': contract_symbol,
            'tickersymbol': row['tickersymbol'],  # Actual contract code (e.g., VN30F2201)
            'price': float(row['price']),
            'bid': float(row['best-bid']),
            'ask': float(row['best-ask']),
            'spread': float(row['spread'])
        }

        self.publish_message(contract_symbol, message_data)

    def _publish_dual_files(self, rate_hz: float = 1.0, max_messages: Optional[int] = None):
        """
        Publish from F1M and F2M files with synchronized reading and conditional F2M publishing

        Algorithm:
        1. Read F1M row by row
        2. For each F1M row, advance F2M index to keep timestamps synchronized
        3. Detect rollover period dynamically (contract code change or near expiration)
        4. Always publish F1M
        5. Only publish F2M during rollover period

        Args:
            rate_hz: Publishing rate (messages per second)
            max_messages: Maximum messages to publish (None = unlimited)
        """
        if not hasattr(self, 'f1m_data') or self.f1m_data is None:
            raise RuntimeError("No F1M/F2M data loaded. Call load_separate_files() first.")

        f1m_data = self.f1m_data
        f2m_data = self.f2m_data

        self.logger.info(f"Starting dual-file publishing")
        self.logger.info(f"F1M rows: {len(f1m_data)}, F2M rows: {len(f2m_data)}")
        self.logger.info(f"Publishing rate: {rate_hz} Hz")
        self.logger.info(f"F2M rollover window: {self.f2m_window_days} days before expiration")

        sleep_time = 1.0 / rate_hz
        messages_sent = 0
        f1_idx = 0
        f2_idx = 0
        previous_f1_contract = None

        try:
            while f1_idx < len(f1m_data):
                # 1. Read F1M row
                f1_row = f1m_data.iloc[f1_idx]
                f1_timestamp = f1_row['datetime']
                f1_contract = f1_row['tickersymbol']
                f1_date = f1_timestamp.date()

                # 2. Detect rollover period dynamically
                should_publish_f2 = self._should_publish_f2m(
                    f1_date,
                    f1_contract,
                    previous_f1_contract
                )

                # 3. Advance F2 index to catch up with F1 timestamp
                # Keep F2 synchronized with F1 by advancing to same or later timestamp
                while f2_idx < len(f2m_data):
                    f2_row = f2m_data.iloc[f2_idx]
                    f2_timestamp = f2_row['datetime']

                    # If F2 timestamp has caught up to F1, process it
                    if f2_timestamp >= f1_timestamp:
                        # Publish F2M only if in rollover period
                        if should_publish_f2:
                            self._publish_row(f2_row, 'VN30F2M')
                            messages_sent += 1

                            # Log progress
                            if messages_sent % 100 == 0:
                                self.logger.info(f"Published {messages_sent} messages (F1+F2 mode)")

                            # Check max messages
                            if max_messages and messages_sent >= max_messages:
                                self.logger.info(f"Reached max messages: {max_messages}")
                                return

                            # Rate limiting
                            time.sleep(sleep_time)

                        # Move to next F2 row
                        f2_idx += 1
                        break

                    # F2 is still behind F1, keep advancing without publishing
                    f2_idx += 1

                # 4. Always publish F1M
                self._publish_row(f1_row, 'VN30F1M')
                messages_sent += 1

                # Log progress
                if messages_sent % 100 == 0:
                    self.logger.info(f"Published {messages_sent} messages")

                # Check max messages
                if max_messages and messages_sent >= max_messages:
                    self.logger.info(f"Reached max messages: {max_messages}")
                    return

                # 5. Update tracking and move to next F1 row
                previous_f1_contract = f1_contract
                f1_idx += 1

                # Rate limiting
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            self.logger.info("Publishing stopped by user")

        finally:
            self.logger.info(f"Dual-file publishing complete")
            self.logger.info(f"Total messages published: {self.messages_published}")
            self.logger.info(f"F1M index: {f1_idx}/{len(f1m_data)}")
            self.logger.info(f"F2M index: {f2_idx}/{len(f2m_data)}")

    def start_publishing(self, rate_hz: float = 1.0, loop: bool = False, max_messages: Optional[int] = None):
        """
        Start publishing from pre-loaded data

        Args:
            rate_hz: Publishing rate (messages per second)
            loop: Whether to loop continuously
            max_messages: Maximum number of messages to publish (None = unlimited)
        """
        if not hasattr(self, 'data') or self.data is None:
            raise RuntimeError("No data loaded. Call load_csv() first.")

        self.logger.info(f"Starting to publish {len(self.data)} rows at {rate_hz} Hz")

        sleep_time = 1.0 / rate_hz
        messages_sent = 0

        try:
            while True:
                for index, row in self.data.iterrows():
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

    def start_publishing_dual(
        self,
        rate_hz: float = 1.0,
        loop: bool = False,
        max_messages: Optional[int] = None
    ):
        """
        Publish from dual F1M and F2M files with conditional F2M subscription

        This method publishes F1M data continuously and conditionally publishes
        F2M data only during rollover periods (detected by contract change or
        proximity to expiration).

        Args:
            rate_hz: Publishing rate (messages per second)
            loop: Whether to loop continuously
            max_messages: Maximum messages to publish (None = unlimited)
        """
        if not hasattr(self, 'f1m_data') or self.f1m_data is None:
            raise RuntimeError("No dual data loaded. Call load_separate_files() first.")

        self.logger.info(f"Starting dual-file publishing at {rate_hz} Hz")
        self.logger.info(f"F1M rows: {len(self.f1m_data)}, F2M rows: {len(self.f2m_data)}")

        sleep_time = 1.0 / rate_hz
        messages_sent = 0
        f2m_active = False
        last_f1_contract = None

        # Merge and sort by timestamp
        f1m_data = self.f1m_data.copy()
        f2m_data = self.f2m_data.copy()

        f1m_data['source'] = 'F1M'
        f2m_data['source'] = 'F2M'

        # Combine and sort by datetime
        combined = pd.concat([f1m_data, f2m_data]).sort_values('datetime').reset_index(drop=True)

        self.logger.info(f"Total combined rows: {len(combined)}")

        try:
            for index, row in combined.iterrows():
                source = row['source']
                current_date = row['datetime'].date()
                contract = row['tickersymbol']

                # Process F1M messages
                if source == 'F1M':
                    # Check if F2M should be activated
                    if last_f1_contract and contract != last_f1_contract:
                        # Rollover detected
                        self.logger.info(f"Rollover detected: {last_f1_contract} -> {contract}")
                        f2m_active = True
                    elif self._is_near_expiration(current_date, contract):
                        # Near expiration
                        if not f2m_active:
                            self.logger.info(f"F2M activated (near expiration): {current_date}")
                        f2m_active = True
                    else:
                        # Check if F2M should be deactivated
                        if f2m_active:
                            if not self._is_near_expiration(current_date, contract):
                                self.logger.info(f"F2M deactivated (outside window): {current_date}")
                                f2m_active = False

                    # Publish F1M message
                    message_data = {
                        'timestamp': row['datetime'].isoformat(),
                        'contract': 'VN30F1M',  # Abstract symbol
                        'tickersymbol': contract,  # Actual contract code
                        'price': float(row['price']),
                        'bid': float(row['best-bid']),
                        'ask': float(row['best-ask']),
                        'spread': float(row['spread'])
                    }
                    self.publish_message('VN30F1M', message_data)
                    messages_sent += 1

                    last_f1_contract = contract

                # Process F2M messages (only if active)
                elif source == 'F2M' and f2m_active:
                    message_data = {
                        'timestamp': row['datetime'].isoformat(),
                        'contract': 'VN30F2M',  # Abstract symbol
                        'tickersymbol': contract,  # Actual contract code
                        'price': float(row['price']) if pd.notna(row['price']) else 0.0,
                        'bid': float(row['best-bid']),
                        'ask': float(row['best-ask']),
                        'spread': float(row['spread'])
                    }
                    self.publish_message('VN30F2M', message_data)
                    messages_sent += 1

                # Log progress
                if messages_sent % 100 == 0:
                    self.logger.info(f"Published {messages_sent} messages (F2M: {'active' if f2m_active else 'inactive'})")

                # Check max messages
                if max_messages and messages_sent >= max_messages:
                    self.logger.info(f"Reached max messages: {max_messages}")
                    return

                # Rate limiting
                time.sleep(sleep_time)

            if loop:
                self.logger.info("Looping back to start...")
                # Recursively call for looping
                self.start_publishing_dual(rate_hz=rate_hz, loop=loop, max_messages=max_messages)

        except KeyboardInterrupt:
            self.logger.info("Publishing stopped by user")

        finally:
            self.logger.info(f"Total messages published: {self.messages_published}")

    def publish_message(self, contract: str, data: dict):
        """
        Publish single message to Redis

        Args:
            contract: Contract symbol
            data: Market data dictionary
        """
        if not self.redis_client:
            raise RuntimeError("Not connected to Redis. Call connect() first.")

        # Normalize contract if enabled (for playback mode)
        normalized_contract = self._normalize_contract(contract)
        channel = f"{self.channel_prefix}:{normalized_contract}"
        message = json.dumps(data)

        self.redis_client.publish(channel, message)
        self.messages_published += 1

    def publish_from_csv(
        self,
        csv_path: Optional[str] = None,
        rate_hz: float = 1.0,
        loop: bool = False,
        max_messages: Optional[int] = None,
        f1m_csv: Optional[str] = None,
        f2m_csv: Optional[str] = None,
        f2m_window_days: int = 3
    ):
        """
        Publish market data from CSV file(s)

        Supports two modes:
        1. Merged file mode (backward compatible): Single CSV with both F1M and F2M data
        2. Dual-file mode: Separate F1M and F2M files with conditional F2M publishing

        Args:
            csv_path: Path to merged CSV file (for backward compatibility)
            rate_hz: Publishing rate (messages per second)
            loop: Whether to loop continuously (merged mode only)
            max_messages: Maximum number of messages to publish (None = unlimited)
            f1m_csv: Path to F1M CSV file (dual-file mode)
            f2m_csv: Path to F2M CSV file (dual-file mode)
            f2m_window_days: Days before expiration to publish F2M (dual-file mode)
        """
        # Mode 1: Dual-file mode
        if f1m_csv and f2m_csv:
            self.logger.info("Using dual-file mode (separate F1M/F2M files)")
            self.load_separate_files(f1m_csv, f2m_csv, f2m_window_days)
            self._publish_dual_files(rate_hz, max_messages)
            return

        # Mode 2: Merged file mode (backward compatible)
        if csv_path:
            self.logger.info("Using merged file mode (single CSV)")
        else:
            raise ValueError("Must provide either csv_path (merged mode) or both f1m_csv and f2m_csv (dual mode)")

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
    parser.add_argument('--csv', help='CSV file to publish (merged mode)')
    parser.add_argument('--f1m-csv', help='F1M CSV file (dual-file mode)')
    parser.add_argument('--f2m-csv', help='F2M CSV file (dual-file mode)')
    parser.add_argument('--f2m-window-days', type=int, default=3, help='Days before expiration to publish F2M')
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
        elif args.f1m_csv and args.f2m_csv:
            # Dual-file mode
            publisher.publish_from_csv(
                f1m_csv=args.f1m_csv,
                f2m_csv=args.f2m_csv,
                f2m_window_days=args.f2m_window_days,
                rate_hz=args.rate,
                max_messages=args.max_messages
            )
        elif args.csv:
            # Merged file mode
            publisher.publish_from_csv(
                csv_path=args.csv,
                rate_hz=args.rate,
                loop=args.loop,
                max_messages=args.max_messages
            )
        else:
            print("Error: Must specify --csv (merged mode), --f1m-csv and --f2m-csv (dual mode), --random, or --sine")
            return 1

    except Exception as e:
        logging.error(f"Error during publishing: {e}", exc_info=True)
        return 1

    return 0


if __name__ == '__main__':
    exit(main())

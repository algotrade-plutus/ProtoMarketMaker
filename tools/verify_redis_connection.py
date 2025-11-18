#!/usr/bin/env python3
"""
Redis Connection and Streaming Test Script
Tests Redis connection, Pub/Sub functionality, and contract resolution
"""

import os
import sys
import json
import time
import redis
import logging
import threading
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dotenv import load_dotenv

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'test_redis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

logger = logging.getLogger('TestRedis')

def mask_password(value: str, show_chars: int = 2) -> str:
    """Mask sensitive information"""
    if not value or len(value) <= show_chars * 2:
        return '***'
    return f"{value[:show_chars]}{'*' * (len(value) - show_chars * 2)}{value[-show_chars:]}"

def load_redis_config() -> Optional[Dict]:
    """Load Redis configuration from .env.redis and config files"""
    logger.info("=" * 60)
    logger.info("STEP 1: Loading Redis Configuration")
    logger.info("=" * 60)

    config = {}

    # Try to load from .env.redis first
    env_file = '.env.redis'
    if os.path.exists(env_file):
        logger.info(f"✅ Found environment file: {env_file}")
        load_dotenv(env_file, override=True)

        # Load environment variables
        env_config = {
            'redis_host': os.getenv('REDIS_HOST'),
            'redis_port': os.getenv('REDIS_PORT'),
            'redis_db': os.getenv('REDIS_DB'),
            'redis_password': os.getenv('REDIS_PASSWORD'),
            'redis_decode_responses': os.getenv('REDIS_DECODE_RESPONSES'),
            'channel_prefix': os.getenv('REDIS_CHANNEL_PREFIX'),
            'auto_detect_contracts': os.getenv('AUTO_DETECT_CONTRACTS')
        }

        # Parse REDIS_CONTRACTS (comma-separated list)
        contracts_str = os.getenv('REDIS_CONTRACTS')
        if contracts_str:
            env_config['contracts'] = [c.strip() for c in contracts_str.split(',')]

        # Parse CONTRACT_MAPPINGS (JSON string)
        mappings_str = os.getenv('CONTRACT_MAPPINGS')
        if mappings_str:
            try:
                env_config['contract_mappings'] = json.loads(mappings_str)
            except json.JSONDecodeError as e:
                logger.warning(f"  ⚠️ Failed to parse CONTRACT_MAPPINGS: {e}")

        # Filter out None values
        env_config = {k: v for k, v in env_config.items() if v is not None}
        config.update(env_config)
        logger.info(f"  Loaded {len(env_config)} settings from .env.redis")
    else:
        logger.warning(f"⚠️ Environment file not found: {env_file}")

    # Try to load from config/redis_config.json
    config_file = 'config/redis_config.json'
    if os.path.exists(config_file):
        logger.info(f"✅ Found config file: {config_file}")
        try:
            with open(config_file, 'r') as f:
                json_config = json.load(f)

            # Only use json config for missing values
            for key, value in json_config.items():
                if key not in config:
                    config[key] = value

            logger.info(f"  Loaded additional settings from {config_file}")
        except Exception as e:
            logger.error(f"  ❌ Error loading {config_file}: {e}")
    else:
        logger.warning(f"⚠️ Config file not found: {config_file}")

    # Apply defaults for critical settings
    defaults = {
        'redis_host': 'localhost',
        'redis_port': 6379,
        'redis_db': 0,
        'redis_password': '',
        'redis_decode_responses': True,
        'channel_prefix': 'market'
    }

    for key, default in defaults.items():
        if key not in config:
            config[key] = default
            logger.info(f"  Using default for {key}: {default}")

    # Convert types
    try:
        config['redis_port'] = int(config['redis_port'])
        config['redis_db'] = int(config['redis_db'])

        # Handle boolean conversion
        if isinstance(config['redis_decode_responses'], str):
            config['redis_decode_responses'] = config['redis_decode_responses'].lower() in ('true', '1', 'yes')

        # Convert auto_detect_contracts to boolean if it's a string
        if 'auto_detect_contracts' in config and isinstance(config['auto_detect_contracts'], str):
            config['auto_detect_contracts'] = config['auto_detect_contracts'].lower() in ('true', '1', 'yes')

    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error converting config values: {e}")
        return None

    # Display loaded configuration
    logger.info("\n📋 Redis Configuration:")
    logger.info(f"  Host: {config['redis_host']}")
    logger.info(f"  Port: {config['redis_port']}")
    logger.info(f"  Database: {config['redis_db']}")
    logger.info(f"  Password: {mask_password(config.get('redis_password', '')) if config.get('redis_password') else 'Not set'}")
    logger.info(f"  Decode responses: {config['redis_decode_responses']}")
    logger.info(f"  Channel prefix: {config.get('channel_prefix', 'market')}")

    # Contract configuration
    if 'contracts' in config:
        logger.info(f"  Contracts: {config['contracts']}")
    if 'auto_detect_contracts' in config:
        logger.info(f"  Auto-detect contracts: {config['auto_detect_contracts']}")
    if 'contract_mappings' in config:
        logger.info(f"  Contract mappings: {config['contract_mappings']}")

    return config

def is_external_server(config: Dict) -> bool:
    """Check if this is an external Redis server (not localhost)"""
    host = config.get('redis_host', 'localhost').lower()
    return host not in ['localhost', '127.0.0.1', '::1']

def test_basic_connection(config: Dict) -> bool:
    """Test basic Redis connection"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Testing Basic Redis Connection")
    logger.info("=" * 60)

    is_external = is_external_server(config)
    if is_external:
        logger.info("🌐 Detected EXTERNAL Redis server - will run read-only tests")
    else:
        logger.info("🏠 Detected LOCAL Redis server - will run full tests")

    try:
        # Create Redis client
        logger.info(f"⏳ Connecting to Redis at {config['redis_host']}:{config['redis_port']}")

        client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True),
            socket_connect_timeout=5,
            socket_timeout=5
        )

        # Test PING
        logger.info("  Testing PING command...")
        response = client.ping()
        if response:
            logger.info("  ✅ PING successful")
        else:
            logger.error("  ❌ PING failed")
            return False

        # For external servers, skip write tests
        if not is_external:
            # Test SET/GET (only for local servers)
            logger.info("  Testing SET/GET commands...")
            test_key = f"test:connection:{datetime.now().timestamp()}"
            test_value = "ProtoMarketMaker Test"

            client.set(test_key, test_value, ex=60)  # Expire after 60 seconds
            retrieved = client.get(test_key)

            if retrieved == test_value:
                logger.info(f"  ✅ SET/GET successful: '{test_value}'")
            else:
                logger.error(f"  ❌ SET/GET failed: expected '{test_value}', got '{retrieved}'")
                return False

            # Clean up
            client.delete(test_key)
            logger.info("  ✅ Cleanup successful")
        else:
            logger.info("  ⏭️ Skipping SET/GET tests for external server (read-only mode)")

        # Get server info
        try:
            info = client.info('server')
            logger.info(f"\n📊 Redis Server Info:")
            logger.info(f"  Version: {info.get('redis_version', 'Unknown')}")
            logger.info(f"  Mode: {info.get('redis_mode', 'Unknown')}")
            logger.info(f"  Connected clients: {client.info('clients').get('connected_clients', 'Unknown')}")
        except:
            logger.warning("  ⚠️ Could not retrieve server info (may require permissions)")

        client.close()
        return True

    except redis.ConnectionError as e:
        logger.error(f"❌ Connection error: {e}")
        logger.error("\n🔍 Possible causes:")
        logger.error("  1. Redis server is not running")
        logger.error("  2. Incorrect host/port")
        logger.error("  3. Network/firewall issues")
        logger.info("\n💡 Try: redis-cli -h {config['redis_host']} -p {config['redis_port']} ping")
        return False

    except redis.AuthenticationError as e:
        logger.error(f"❌ Authentication error: {e}")
        logger.error("\n🔍 Password is required but incorrect or not provided")
        logger.info("  Check REDIS_PASSWORD in .env.redis")
        return False

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        logger.error(traceback.format_exc())
        return False

def test_pubsub(config: Dict) -> bool:
    """Test Redis Pub/Sub functionality"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: Testing Pub/Sub Functionality")
    logger.info("=" * 60)

    is_external = is_external_server(config)

    try:
        if is_external:
            # For external servers, only test subscription
            logger.info("🌐 External server detected - testing subscription only")
            return test_external_subscription(config)

        # For local servers, test full pub/sub
        logger.info("🏠 Local server - testing full Pub/Sub")

        # Create publisher and subscriber clients
        pub_client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True),
            socket_connect_timeout=5
        )

        sub_client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True),
            socket_connect_timeout=5
        )

        # Create pubsub object
        pubsub = sub_client.pubsub()

        # Test channel
        channel_prefix = config.get('channel_prefix', 'market')
        test_channel = f"{channel_prefix}:test:channel"

        logger.info(f"  Subscribing to channel: {test_channel}")
        pubsub.subscribe(test_channel)

        # Allow subscription to be established
        time.sleep(0.5)

        # Publish test messages
        test_messages = [
            {"type": "test", "data": "Message 1", "timestamp": datetime.now().isoformat()},
            {"type": "test", "data": "Message 2", "timestamp": datetime.now().isoformat()},
            {"type": "test", "data": "Message 3", "timestamp": datetime.now().isoformat()}
        ]

        logger.info(f"  Publishing {len(test_messages)} test messages...")
        for msg in test_messages:
            pub_client.publish(test_channel, json.dumps(msg))
            time.sleep(0.1)

        # Receive messages
        logger.info("  Receiving messages...")
        received = []
        timeout = time.time() + 5  # 5 second timeout

        while time.time() < timeout:
            message = pubsub.get_message(timeout=1)
            if message and message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    received.append(data)
                    logger.info(f"    ✅ Received: {data['data']}")
                except:
                    pass

            if len(received) >= len(test_messages):
                break

        # Check results
        if len(received) == len(test_messages):
            logger.info(f"  ✅ Pub/Sub test successful: {len(received)}/{len(test_messages)} messages received")
        else:
            logger.error(f"  ❌ Pub/Sub test failed: {len(received)}/{len(test_messages)} messages received")
            return False

        # Cleanup
        pubsub.unsubscribe(test_channel)
        pubsub.close()
        pub_client.close()
        sub_client.close()

        return True

    except Exception as e:
        logger.error(f"❌ Pub/Sub test error: {e}")
        logger.error(traceback.format_exc())
        return False

def test_external_subscription(config: Dict) -> bool:
    """Test subscription to market channels on external server (read-only)"""
    logger.info("\n📡 Testing subscription to market channels...")

    try:
        # Import contract resolver
        from utils.contract_resolver import ContractSymbolResolver

        # Create subscriber client
        sub_client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True),
            socket_connect_timeout=5
        )

        # Create pubsub object
        pubsub = sub_client.pubsub()

        # Setup contract resolution
        channel_prefix = config.get('channel_prefix', '')
        contracts = config.get('contracts', ['VN30F1M', 'VN30F2M'])
        auto_detect = config.get('auto_detect_contracts', False)
        contract_mappings = config.get('contract_mappings', {})

        # Create resolver
        if contract_mappings:
            resolver = ContractSymbolResolver(
                manual_mappings=contract_mappings,
                auto_detect=False
            )
        else:
            resolver = ContractSymbolResolver(auto_detect=auto_detect)

        channels = []

        for contract in contracts:
            # Resolve contract symbol
            resolved = resolver.resolve(contract)

            if channel_prefix:
                channel = f"{channel_prefix}:{resolved}"
            else:
                channel = resolved

            channels.append(channel)
            pubsub.subscribe(channel)
            logger.info(f"  ✅ Subscribed to: {channel}")
            if resolved != contract:
                logger.info(f"     (Resolved {contract} → {resolved})")

        # Wait for messages (with timeout)
        logger.info("\n  ⏳ Waiting for market data (10 seconds)...")
        received_count = 0
        timeout = time.time() + 10  # 10 second timeout

        while time.time() < timeout:
            message = pubsub.get_message(timeout=1)
            if message and message['type'] == 'message':
                received_count += 1
                try:
                    data = json.loads(message['data'])
                    timestamp_raw = data.get('timestamp', None)
                    if timestamp_raw and isinstance(timestamp_raw, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp_raw).isoformat()
                    else:
                        timestamp = 'N/A'
                    matched_price = data.get('latest_matched_price', 'N/A')
                    bid1 = data.get('bid_price_1', 'N/A')
                    ask1 = data.get('ask_price_1', 'N/A')
                    logger.info(f"    📨 {message['channel']} | timestamp={timestamp} | matched_price={matched_price} | bid1={bid1} | ask1={ask1}")
                except Exception as e:
                    logger.warning(f"    ⚠️ Received non-JSON message: {message['data'][:100]}...")

        if received_count == 0:
            logger.warning("  ⚠️ No market data received (market may be closed or no active publishers)")
            logger.info("  This is normal if market is closed. Subscription capability confirmed.")
        else:
            logger.info(f"  ✅ Received {received_count} market messages")

        # Cleanup
        for channel in channels:
            pubsub.unsubscribe(channel)
        pubsub.close()
        sub_client.close()

        return True  # Return success if we could subscribe, even if no messages

    except Exception as e:
        logger.error(f"❌ External subscription test error: {e}")
        logger.error(traceback.format_exc())
        return False

def test_contract_resolution(config: Dict) -> bool:
    """Test contract symbol resolution feature"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: Testing Contract Symbol Resolution")
    logger.info("=" * 60)

    is_external = is_external_server(config)

    try:
        # Import contract resolver
        from utils.contract_resolver import ContractSymbolResolver

        logger.info("✅ Successfully imported ContractSymbolResolver")

        # Test configuration
        contracts = config.get('contracts', ['VN30F1M', 'VN30F2M'])
        auto_detect = config.get('auto_detect_contracts', False)
        contract_mappings = config.get('contract_mappings', {})

        logger.info(f"\n📋 Contract Configuration:")
        logger.info(f"  Abstract contracts: {contracts}")
        logger.info(f"  Auto-detect enabled: {auto_detect}")
        logger.info(f"  Custom mappings: {contract_mappings}")

        # Create resolver with custom mappings if provided
        if contract_mappings:
            resolver = ContractSymbolResolver(
                manual_mappings=contract_mappings,
                auto_detect=False  # Manual mappings override auto-detect
            )
            for abstract, concrete in contract_mappings.items():
                logger.info(f"  Using mapping: {abstract} → {concrete}")
        else:
            resolver = ContractSymbolResolver(auto_detect=auto_detect)

        # Test resolution for each contract
        logger.info("\n🔄 Testing contract resolution:")

        for contract in contracts:
            logger.info(f"\n  Testing: {contract}")

            # Resolve the contract
            resolved = resolver.resolve(contract)
            logger.info(f"    Resolved to: {resolved}")

            # Get expiration info if available
            try:
                if auto_detect and resolved != contract:
                    # This means auto-detection worked
                    logger.info(f"    ✅ Auto-detection successful")

                    # Try to get expiration date
                    exp_date = resolver.get_expiration_date(resolved)
                    if exp_date:
                        logger.info(f"    Expiration: {exp_date.strftime('%Y-%m-%d')}")
                        # Convert date to datetime for comparison
                        from datetime import date as dt_date
                        today = datetime.now().date() if isinstance(datetime.now(), datetime) else datetime.now()
                        if isinstance(exp_date, dt_date):
                            days_to_exp = (exp_date - today).days
                            logger.info(f"    Days to expiration: {days_to_exp}")
                elif resolved == contract:
                    logger.info(f"    ⚠️ Using abstract symbol (no auto-detection)")
                else:
                    logger.info(f"    ✅ Using custom mapping")

            except Exception as e:
                logger.warning(f"    ⚠️ Could not get expiration info: {e}")

        # Test channels for contracts
        logger.info("\n📡 Testing Redis channels for contracts:")

        client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True)
        )

        channel_prefix = config.get('channel_prefix', 'market')

        for contract in contracts:
            resolved = resolver.resolve(contract)
            channel = f"{channel_prefix}:{resolved}"

            logger.info(f"\n  Contract: {contract} → {resolved}")
            logger.info(f"    Channel: {channel}")

            if not is_external:
                # Try to publish a test tick (only for local servers)
                test_tick = {
                    "contract": resolved,
                    "price": 1234.5,
                    "timestamp": datetime.now().isoformat(),
                    "type": "test"
                }

                try:
                    num_subscribers = client.publish(channel, json.dumps(test_tick))
                    logger.info(f"    ✅ Published test tick (subscribers: {num_subscribers})")
                except Exception as e:
                    logger.error(f"    ❌ Failed to publish: {e}")
            else:
                logger.info("    ⏭️ Skipping publish test for external server (read-only)")

        client.close()
        return True

    except ImportError as e:
        logger.error(f"❌ Failed to import ContractSymbolResolver: {e}")
        logger.error("Make sure utils/contract_resolver.py exists")
        return False

    except Exception as e:
        logger.error(f"❌ Contract resolution test error: {e}")
        logger.error(traceback.format_exc())
        return False

def test_streaming_simulation(config: Dict) -> bool:
    """Simulate streaming market data"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 5: Testing Market Data Streaming")
    logger.info("=" * 60)

    is_external = is_external_server(config)

    if is_external:
        logger.info("🌐 External server detected - testing subscription to live streams")
        return test_external_streaming(config)
    else:
        logger.info("🏠 Local server - testing full publish/subscribe simulation")
        return test_local_streaming_simulation(config)

def test_local_streaming_simulation(config: Dict) -> bool:
    """Test streaming with local publishing (for local servers)"""
    try:
        # Import contract resolver
        from utils.contract_resolver import ContractSymbolResolver

        # Create clients
        pub_client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True)
        )

        sub_client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True)
        )

        # Setup contract resolution
        channel_prefix = config.get('channel_prefix', 'market')
        contracts = config.get('contracts', ['VN30F1M', 'VN30F2M'])
        auto_detect = config.get('auto_detect_contracts', False)
        contract_mappings = config.get('contract_mappings', {})

        # Create resolver
        if contract_mappings:
            resolver = ContractSymbolResolver(
                manual_mappings=contract_mappings,
                auto_detect=False
            )
        else:
            resolver = ContractSymbolResolver(auto_detect=auto_detect)

        # Subscribe to all contract channels (with resolution)
        pubsub = sub_client.pubsub()
        channels = []
        resolved_contracts = []

        for contract in contracts:
            # Resolve contract symbol
            resolved = resolver.resolve(contract)
            resolved_contracts.append(resolved)

            channel = f"{channel_prefix}:{resolved}"
            channels.append(channel)
            pubsub.subscribe(channel)
            logger.info(f"  Subscribed to: {channel}")
            if resolved != contract:
                logger.info(f"     (Resolved {contract} → {resolved})")

        time.sleep(0.5)  # Allow subscriptions to establish

        # Start receiver thread
        received_messages = []
        stop_event = threading.Event()

        def receiver():
            """Background thread to receive messages"""
            while not stop_event.is_set():
                try:
                    message = pubsub.get_message(timeout=0.1)
                    if message and message['type'] == 'message':
                        try:
                            data = json.loads(message['data'])
                            received_messages.append(data)
                            logger.info(f"    📨 Received: {data.get('contract', 'unknown')} @ {data.get('price', 'N/A')}")
                        except:
                            pass
                except:
                    break

        receiver_thread = threading.Thread(target=receiver, daemon=True)
        receiver_thread.start()
        logger.info("  ✅ Started receiver thread")

        # Simulate market data publishing
        logger.info("\n  📤 Publishing simulated market data...")

        # Use resolved contract symbols for base prices
        base_prices = {'VN30F2511': 1580.0, 'VN30F2512': 1582.5}

        for i in range(10):  # Publish 10 ticks
            for idx, contract in enumerate(contracts):
                # Get the resolved contract symbol
                resolved = resolved_contracts[idx]

                # Simulate price movement
                base_price = base_prices.get(resolved, 1580.0)
                price = base_price + (i - 5) * 0.5  # Price moves ±2.5 points

                tick = {
                    "contract": resolved,  # Use resolved contract
                    "price": price,
                    "bid": price - 0.5,
                    "ask": price + 0.5,
                    "volume": 100 + i * 10,
                    "timestamp": datetime.now().isoformat(),
                    "sequence": i
                }

                channel = f"{channel_prefix}:{resolved}"  # Use resolved contract
                pub_client.publish(channel, json.dumps(tick))
                if resolved != contract:
                    logger.info(f"    📤 Published: {resolved} (from {contract}) @ {price}")
                else:
                    logger.info(f"    📤 Published: {resolved} @ {price}")

            time.sleep(0.2)  # 200ms between ticks

        # Wait for messages to be received
        time.sleep(1)

        # Stop receiver
        stop_event.set()
        receiver_thread.join(timeout=2)

        # Check results
        logger.info(f"\n  📊 Streaming Results:")
        logger.info(f"    Published: {10 * len(contracts)} messages")
        logger.info(f"    Received: {len(received_messages)} messages")

        if len(received_messages) >= 10 * len(contracts) * 0.8:  # Allow 20% loss
            logger.info("  ✅ Streaming simulation successful")
            success = True
        else:
            logger.error("  ❌ Streaming simulation failed - too many messages lost")
            success = False

        # Cleanup
        for channel in channels:
            pubsub.unsubscribe(channel)
        pubsub.close()
        pub_client.close()
        sub_client.close()

        return success

    except Exception as e:
        logger.error(f"❌ Local streaming simulation error: {e}")
        logger.error(traceback.format_exc())
        return False

def test_external_streaming(config: Dict) -> bool:
    """Test streaming by consuming from live market data (for external servers)"""
    try:
        # Import contract resolver
        from utils.contract_resolver import ContractSymbolResolver

        # Create subscriber client only
        sub_client = redis.Redis(
            host=config['redis_host'],
            port=config['redis_port'],
            db=config['redis_db'],
            password=config.get('redis_password') or None,
            decode_responses=config.get('redis_decode_responses', True),
            socket_connect_timeout=5
        )

        # Setup contract resolution
        channel_prefix = config.get('channel_prefix', 'market')
        contracts = config.get('contracts', ['VN30F1M', 'VN30F2M'])
        auto_detect = config.get('auto_detect_contracts', False)
        contract_mappings = config.get('contract_mappings', {})

        # Create resolver
        if contract_mappings:
            resolver = ContractSymbolResolver(
                manual_mappings=contract_mappings,
                auto_detect=False
            )
        else:
            resolver = ContractSymbolResolver(auto_detect=auto_detect)

        # Subscribe to all contract channels (with resolution)
        pubsub = sub_client.pubsub()
        channels = []

        logger.info("  📡 Subscribing to market channels:")
        for contract in contracts:
            # Resolve contract symbol
            resolved = resolver.resolve(contract)
            channel = f"{channel_prefix}:{resolved}"
            channels.append(channel)
            pubsub.subscribe(channel)
            logger.info(f"    ✅ Subscribed to: {channel}")
            if resolved != contract:
                logger.info(f"       (Resolved {contract} → {resolved})")

        # Collect market data
        logger.info("\n  ⏳ Listening for market data (15 seconds)...")
        logger.info("    (If market is closed, no data will be received)")

        received_messages = []
        message_counts = {}
        timeout = time.time() + 15  # 15 second timeout for external servers

        while time.time() < timeout:
            try:
                message = pubsub.get_message(timeout=1)
                if message and message['type'] == 'message':
                    channel_name = message['channel']
                    if channel_name not in message_counts:
                        message_counts[channel_name] = 0
                    message_counts[channel_name] += 1

                    try:
                        data = json.loads(message['data'])
                        received_messages.append(data)

                        # Log all messages
                        timestamp_raw = data.get('timestamp', None)
                        if timestamp_raw and isinstance(timestamp_raw, (int, float)):
                            timestamp = datetime.fromtimestamp(timestamp_raw).isoformat()
                        else:
                            timestamp = 'N/A'
                        matched_price = data.get('latest_matched_price', 'N/A')
                        bid1 = data.get('bid_price_1', 'N/A')
                        ask1 = data.get('ask_price_1', 'N/A')
                        logger.info(f"    📨 {channel_name} | timestamp={timestamp} | matched_price={matched_price} | bid1={bid1} | ask1={ask1}")

                    except json.JSONDecodeError:
                        logger.debug(f"    Non-JSON message received")
                    except Exception as e:
                        logger.debug(f"    Error processing message: {e}")

            except Exception as e:
                logger.debug(f"Error in receive loop: {e}")
                continue

        # Results
        logger.info(f"\n  📊 External Streaming Results:")
        total_received = len(received_messages)

        if total_received > 0:
            logger.info(f"    ✅ Total messages received: {total_received}")
            for channel, count in message_counts.items():
                logger.info(f"    📈 {channel}: {count} messages")
            logger.info("  ✅ External streaming test successful")
            success = True
        else:
            logger.warning("  ⚠️ No market data received")
            logger.info("  Possible reasons:")
            logger.info("    1. Market is closed (outside trading hours)")
            logger.info("    2. No active publishers on these channels")
            logger.info("    3. Channel names might be different")
            logger.info("  Subscription capability confirmed - connection is working")
            success = True  # Still consider it success if we can subscribe

        # Cleanup
        for channel in channels:
            pubsub.unsubscribe(channel)
        pubsub.close()
        sub_client.close()

        return success

    except Exception as e:
        logger.error(f"❌ External streaming test error: {e}")
        logger.error(traceback.format_exc())
        return False

def main():
    """Main entry point"""
    print("\n" + "=" * 60)
    print("Redis Connection and Streaming Test")
    print("=" * 60)

    # Load configuration
    config = load_redis_config()
    if not config:
        logger.error("❌ Failed to load configuration")
        sys.exit(1)

    # Track test results
    results = {}

    # Test 1: Basic connection
    results['basic_connection'] = test_basic_connection(config)

    # Test 2: Pub/Sub
    if results['basic_connection']:
        results['pubsub'] = test_pubsub(config)
    else:
        logger.warning("⚠️ Skipping Pub/Sub test due to connection failure")
        results['pubsub'] = False

    # Test 3: Contract resolution
    if results['basic_connection']:
        results['contract_resolution'] = test_contract_resolution(config)
    else:
        logger.warning("⚠️ Skipping contract resolution test due to connection failure")
        results['contract_resolution'] = False

    # Test 4: Streaming simulation
    if results['pubsub']:
        results['streaming'] = test_streaming_simulation(config)
    else:
        logger.warning("⚠️ Skipping streaming simulation due to Pub/Sub failure")
        results['streaming'] = False

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name.replace('_', ' ').title()}: {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✅ All tests passed! Redis connection and streaming are working.")
        logger.info("✅ All tests completed successfully")

        print("\n💡 Next steps:")
        print("  1. Start the Redis publisher: python -m tools.redis_publisher")
        print("  2. Run paper trading: python -m paper_trading.runner")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the logs above for details.")
        logger.error("❌ Some tests failed")
        logger.info(f"\n📄 Detailed logs saved to: test_redis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        sys.exit(1)

if __name__ == "__main__":
    main()
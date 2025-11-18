#!/usr/bin/env python3
"""
PaperBroker FIX Connection Test Script
Tests connection to PaperBroker FIX server with detailed logging
"""

import os
import sys
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'test_connection_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

logger = logging.getLogger('TestConnection')

def mask_password(value, show_chars=2):
    """Mask sensitive information, showing only first and last characters"""
    if not value or len(value) <= show_chars * 2:
        return '***'
    return f"{value[:show_chars]}{'*' * (len(value) - show_chars * 2)}{value[-show_chars:]}"

def validate_env_vars():
    """Validate that all required environment variables are present"""
    logger.info("=" * 60)
    logger.info("STEP 1: Validating environment variables")
    logger.info("=" * 60)

    env_file = '.env.paperbroker'
    if os.path.exists(env_file):
        logger.info(f"✅ Found environment file: {env_file}")
        load_dotenv(env_file, override=True)
    else:
        logger.warning(f"⚠️ Environment file not found: {env_file}")
        logger.info("Attempting to load from system environment variables...")

    required_vars = {
        'PAPERBROKER_FIX_HOST': 'FIX server hostname',
        'PAPERBROKER_FIX_PORT': 'FIX server port',
        'PAPERBROKER_SENDER_COMP_ID': 'Sender CompID',
        'PAPERBROKER_TARGET_COMP_ID': 'Target CompID',
        'PAPERBROKER_FIX_USERNAME': 'FIX username',
        'PAPERBROKER_FIX_PASSWORD': 'FIX password'
    }

    optional_vars = {
        'PAPERBROKER_REST_BASE_URL': 'REST API base URL',
        'PAPERBROKER_SUB_ACCOUNT': 'Sub-account ID'
    }

    missing_vars = []
    config = {}

    logger.info("\n📋 Required configuration:")
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            if 'PASSWORD' in var:
                display_value = mask_password(value)
            else:
                display_value = value
            logger.info(f"  ✅ {var}: {display_value} ({description})")
            config[var] = value
        else:
            logger.error(f"  ❌ {var}: NOT SET ({description})")
            missing_vars.append(var)

    logger.info("\n📋 Optional configuration:")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            logger.info(f"  ✅ {var}: {value} ({description})")
            config[var] = value
        else:
            logger.info(f"  ⚠️ {var}: NOT SET ({description}) - using defaults")
            if var == 'PAPERBROKER_SUB_ACCOUNT':
                config[var] = 'D1'

    if missing_vars:
        logger.error(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables in .env.paperbroker file or system environment")
        return None

    return config

def test_connection(config):
    """Test the PaperBroker FIX connection"""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Initializing PaperBroker connector")
    logger.info("=" * 60)

    try:
        # Import here to catch any import errors
        from connectors.paperbroker_connector import PaperBrokerConnector
        from core.event import EventBus
        logger.info("✅ Successfully imported required modules")
    except ImportError as e:
        logger.error(f"❌ Failed to import modules: {e}")
        logger.error("Make sure you're in the correct directory and dependencies are installed")
        return False

    # Parse configuration
    try:
        fix_host = config['PAPERBROKER_FIX_HOST']
        fix_port = int(config.get('PAPERBROKER_FIX_PORT', 5001))
        sender_comp_id = config['PAPERBROKER_SENDER_COMP_ID']
        target_comp_id = config['PAPERBROKER_TARGET_COMP_ID']
        username = config['PAPERBROKER_FIX_USERNAME']
        password = config['PAPERBROKER_FIX_PASSWORD']
        rest_base_url = config.get('PAPERBROKER_REST_BASE_URL')
        sub_account = config.get('PAPERBROKER_SUB_ACCOUNT', 'D1')

        logger.info(f"\n📡 Connection parameters:")
        logger.info(f"  Host: {fix_host}:{fix_port}")
        logger.info(f"  Sender CompID: {sender_comp_id}")
        logger.info(f"  Target CompID: {target_comp_id}")
        logger.info(f"  Username: {username}")
        logger.info(f"  Password: {mask_password(password)}")
        logger.info(f"  REST URL: {rest_base_url or 'Not configured'}")
        logger.info(f"  Sub-account: {sub_account}")

    except (ValueError, KeyError) as e:
        logger.error(f"❌ Error parsing configuration: {e}")
        return False

    # Create event bus and connector
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: Creating connector instance")
    logger.info("=" * 60)

    try:
        event_bus = EventBus()
        logger.info("✅ Created EventBus")

        connector = PaperBrokerConnector(
            event_bus=event_bus,
            fix_host=fix_host,
            fix_port=fix_port,
            sender_comp_id=sender_comp_id,
            target_comp_id=target_comp_id,
            username=username,
            password=password,
            rest_base_url=rest_base_url,
            default_sub_account=sub_account
        )
        logger.info("✅ Created PaperBrokerConnector instance")

    except Exception as e:
        logger.error(f"❌ Failed to create connector: {e}")
        logger.error(traceback.format_exc())
        return False

    # Attempt connection
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: Attempting FIX connection")
    logger.info("=" * 60)

    logger.info(f"⏳ Attempting to connect to {fix_host}:{fix_port} with 10 second timeout...")

    try:
        # Enable debug logging for the connector
        connector_logger = logging.getLogger('PaperBrokerConnector')
        connector_logger.setLevel(logging.DEBUG)

        connection_result = connector.connect(timeout=10)

        if connection_result:
            logger.info("\n" + "🎉" * 20)
            logger.info("✅ CONNECTION SUCCESSFUL!")
            logger.info("🎉" * 20)

            # Try to get some status information
            try:
                if hasattr(connector, 'is_connected'):
                    logger.info(f"Connection status: {connector.is_connected()}")
                if hasattr(connector, 'session_id'):
                    logger.info(f"Session ID: {connector.session_id}")
            except:
                pass

            # Disconnect
            logger.info("\n⏳ Disconnecting...")
            connector.disconnect()
            logger.info("✅ Disconnected successfully")
            return True
        else:
            logger.error("\n" + "❌" * 20)
            logger.error("CONNECTION FAILED!")
            logger.error("❌" * 20)

            logger.error("\n🔍 Possible causes:")
            logger.error("  1. FIX server is not running or unreachable")
            logger.error("  2. Incorrect host/port configuration")
            logger.error("  3. Invalid credentials (username/password)")
            logger.error("  4. CompID mismatch (sender/target)")
            logger.error("  5. Network/firewall issues")
            logger.error("  6. Server rejected connection")

            logger.info("\n💡 Troubleshooting steps:")
            logger.info("  1. Verify FIX server is running: telnet {fix_host} {fix_port}")
            logger.info("  2. Check credentials with server administrator")
            logger.info("  3. Review server logs for rejection reasons")
            logger.info("  4. Check network connectivity to server")
            logger.info("  5. Verify CompID configuration matches server expectations")

            return False

    except Exception as e:
        logger.error(f"\n❌ Exception during connection attempt: {e}")
        logger.error("Full stack trace:")
        logger.error(traceback.format_exc())

        # Try to provide more specific guidance based on error type
        error_msg = str(e).lower()
        if 'timeout' in error_msg:
            logger.error("\n🔍 Timeout error - server may be unreachable or not responding")
            logger.info(f"Try: telnet {fix_host} {fix_port}")
        elif 'refused' in error_msg or 'connection' in error_msg:
            logger.error("\n🔍 Connection refused - server may be down or port incorrect")
        elif 'auth' in error_msg or 'logon' in error_msg:
            logger.error("\n🔍 Authentication error - check username/password")

        return False

def main():
    """Main entry point"""
    print("\n" + "=" * 60)
    print("PaperBroker FIX Connection Test")
    print("=" * 60)

    # Validate environment variables
    config = validate_env_vars()
    if not config:
        logger.error("\n❌ Cannot proceed without required configuration")
        sys.exit(1)

    # Test connection
    success = test_connection(config)

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    if success:
        print("✅ All tests passed! Connection is working.")
        logger.info("✅ Test completed successfully")
        sys.exit(0)
    else:
        print("❌ Connection test failed. Check the logs above for details.")
        logger.error("❌ Test failed")
        logger.info(f"\n📄 Detailed logs saved to: test_connection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        sys.exit(1)

if __name__ == "__main__":
    main()

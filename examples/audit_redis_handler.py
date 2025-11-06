#!/usr/bin/env python3
"""
Audit RedisMarketDataHandler - Complete Diagnostic Script

Tests all aspects of the RedisMarketDataHandler to identify any issues.
"""
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.event import EventBus, MarketDataEvent
from core.enums import EventType
from data.redis_stream import RedisMarketDataHandler


def audit_redis_handler():
    """Complete audit of RedisMarketDataHandler functionality"""

    print("=" * 80)
    print("REDIS MARKET DATA HANDLER - COMPLETE AUDIT")
    print("=" * 80)

    # Step 1: Create EventBus and track events
    print("\n[Step 1] Creating EventBus...")
    event_bus = EventBus()

    received_events = []

    def event_listener(event: MarketDataEvent):
        """Capture events published to the bus"""
        received_events.append(event)
        print(f"  ✓ Event received: {event.contract} @ {event.price} (bid={event.bid}, ask={event.ask})")

    # Subscribe to market data events
    event_bus.subscribe(EventType.MARKET_DATA, event_listener)
    print("✓ EventBus created and listener subscribed")

    # Step 2: Create RedisMarketDataHandler
    print("\n[Step 2] Creating RedisMarketDataHandler...")
    handler = RedisMarketDataHandler(
        event_bus=event_bus,
        redis_host='localhost',
        redis_port=6379,
        channel_prefix='market',
        mode='playback',
        f2m_window_days=3
    )
    print("✓ Handler created")
    print(f"  Mode: {handler.mode}")
    print(f"  Redis: {handler.redis_host}:{handler.redis_port}")
    print(f"  Channel prefix: {handler.channel_prefix}")

    # Step 3: Connect to Redis
    print("\n[Step 3] Connecting to Redis...")
    if not handler.connect():
        print("❌ FAILED to connect to Redis!")
        print("\nPlease ensure:")
        print("  1. Redis server is running (redis-server)")
        print("  2. Redis is accessible on localhost:6379")
        return

    print("✓ Connected to Redis successfully")
    print(f"  Redis client: {handler.redis_client}")
    print(f"  PubSub object: {handler.pubsub}")

    # Step 4: Subscribe to contracts
    print("\n[Step 4] Subscribing to contracts...")
    handler.subscribe(['VN30F1M'])
    print("✓ Subscribed to contracts")
    print(f"  Subscribed contracts: {handler.subscribed_contracts}")
    print(f"  F1M contract: {handler.f1m_contract}")
    print(f"  F2M subscribed: {handler.f2m_subscribed}")

    # Step 5: Start the handler
    print("\n[Step 5] Starting handler...")
    handler.start()
    print("✓ Handler started")
    print(f"  Running: {handler.running}")
    print(f"  Listener thread: {handler.listener_thread}")
    print(f"  Thread alive: {handler.listener_thread.is_alive() if handler.listener_thread else 'No thread'}")

    # Step 6: Monitor for messages
    print("\n[Step 6] Monitoring for 10 seconds...")
    print("Expecting messages from publisher on channel 'market:VN30F1M'")
    print("-" * 80)

    start_time = time.time()
    last_received = 0
    last_processed = 0

    for i in range(10):
        time.sleep(1)

        # IMPORTANT: Process queued events to dispatch to listeners
        event_bus.process_events()

        # Get current statistics
        stats = handler.get_statistics()
        received = stats['messages_received']
        processed = stats['messages_processed']
        failed = stats['messages_failed']

        new_received = received - last_received
        new_processed = processed - last_processed

        status = "✓" if new_received > 0 else "○"
        print(f"  [{i+1}s] {status} Received: +{new_received} (total: {received}) | "
              f"Processed: +{new_processed} (total: {processed}) | "
              f"Failed: {failed} | "
              f"Events captured: {len(received_events)}")

        last_received = received
        last_processed = processed

    # Step 7: Stop the handler
    print("\n[Step 7] Stopping handler...")
    handler.stop()
    print("✓ Handler stopped")

    # Step 8: Final analysis
    print("\n" + "=" * 80)
    print("AUDIT RESULTS")
    print("=" * 80)

    final_stats = handler.get_statistics()

    print("\nStatistics:")
    print(f"  Messages received:  {final_stats['messages_received']}")
    print(f"  Messages processed: {final_stats['messages_processed']}")
    print(f"  Messages failed:    {final_stats['messages_failed']}")
    print(f"  Reconnect count:    {final_stats['reconnect_count']}")
    print(f"  Events captured:    {len(received_events)}")
    print(f"  Last message time:  {final_stats['last_message_time']}")

    print("\nHandler state:")
    print(f"  Running: {handler.running}")
    print(f"  F1M contract: {handler.f1m_contract}")
    print(f"  F2M subscribed: {handler.f2m_subscribed}")

    # Detailed diagnosis
    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)

    if final_stats['messages_received'] == 0:
        print("\n❌ NO MESSAGES RECEIVED")
        print("\nPossible causes:")
        print("  1. Publisher not running or stopped")
        print("  2. Publisher using different channel prefix")
        print("  3. Publisher finished sending all data (loop=False)")
        print("  4. Network/connection issue")

        print("\nTo fix:")
        print("  • Check publisher is running:")
        print("    python examples/test_dual_file_publishing.py publisher")
        print("  • Verify channel with redis-cli:")
        print("    redis-cli SUBSCRIBE market:VN30F1M")

    elif final_stats['messages_received'] != final_stats['messages_processed']:
        print("\n⚠️  MESSAGES RECEIVED BUT NOT ALL PROCESSED")
        print(f"\nReceived: {final_stats['messages_received']}")
        print(f"Processed: {final_stats['messages_processed']}")
        print(f"Failed: {final_stats['messages_failed']}")
        print("\nSome messages failed to process. Check logs for errors.")

    elif len(received_events) != final_stats['messages_processed']:
        print("\n⚠️  MESSAGES PROCESSED BUT NOT ALL PUBLISHED TO EVENTBUS")
        print(f"\nProcessed: {final_stats['messages_processed']}")
        print(f"Events captured: {len(received_events)}")
        print("\nEventBus may have an issue or listener not working correctly.")

    else:
        print(f"\n✅ SUCCESS - Handler working correctly!")
        print(f"\nReceived and processed {final_stats['messages_received']} messages")
        print(f"All {len(received_events)} events successfully published to EventBus")

        if received_events:
            print("\nSample events:")
            for i, event in enumerate(received_events[:3]):
                print(f"  [{i+1}] {event.timestamp} | {event.contract} | "
                      f"Price: {event.price} | Bid: {event.bid} | Ask: {event.ask}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        audit_redis_handler()
    except KeyboardInterrupt:
        print("\n\nAudit interrupted by user")
    except Exception as e:
        print(f"\n\n❌ ERROR during audit: {e}")
        import traceback
        traceback.print_exc()

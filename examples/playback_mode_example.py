"""
Playback Mode Example - Complete Demonstration

This example demonstrates running the paper trading engine in playback mode with:
- Historical CSV data playback
- Abstract contract symbols (VN30F1M, VN30F2M)
- Conditional F2M subscription during rollover windows
- Performance monitoring and results tracking

Prerequisites:
- Redis server running on localhost:6379
- Separate F1M/F2M data files:
  - data/sample/VN30F1M_rollover.csv
  - data/sample/VN30F2M_rollover.csv

Usage:
    python examples/playback_mode_example.py
"""

import time
import threading
from decimal import Decimal
from pathlib import Path

from tools.redis_publisher import RedisMarketDataPublisher
from paper_trading.engine import RedisPaperTradingEngine


def main():
    print("=" * 80)
    print("Playback Mode Example - Dual-File Historical Data Playback")
    print("=" * 80)
    print()

    # Configuration
    f1m_path = 'data/sample/VN30F1M_rollover.csv'
    f2m_path = 'data/sample/VN30F2M_rollover.csv'
    initial_capital = Decimal('500000')
    step = Decimal('2.9')
    duration_seconds = 60
    publish_rate_hz = 50  # 50 messages per second
    f2m_window_days = 3  # Subscribe to F2M within 3 days of expiration

    # Verify data files exist
    if not Path(f1m_path).exists() or not Path(f2m_path).exists():
        print(f"❌ Error: Sample data not found")
        print(f"   F1M: {f1m_path} {'✓' if Path(f1m_path).exists() else '✗'}")
        print(f"   F2M: {f2m_path} {'✓' if Path(f2m_path).exists() else '✗'}")
        print()
        print("Please ensure you have dual-file sample data. You can:")
        print("1. Run: python tools/create_sample_data_from_merged.py")
        print("2. Or download from the project repository")
        return

    print("📋 Configuration:")
    print(f"   F1M Data: {f1m_path}")
    print(f"   F2M Data: {f2m_path}")
    print(f"   Initial Capital: {initial_capital:,} VND")
    print(f"   Step Parameter: {step}")
    print(f"   Duration: {duration_seconds}s")
    print(f"   Publish Rate: {publish_rate_hz} Hz")
    print(f"   F2M Window: {f2m_window_days} days before expiration")
    print()

    # Step 1: Create and connect Redis publisher
    print("Step 1/4: Creating Redis publisher...")
    publisher = RedisMarketDataPublisher(
        redis_host='localhost',
        redis_port=6379,
        channel_prefix='market'
    )

    if not publisher.connect():
        print("❌ Error: Could not connect to Redis server")
        print()
        print("Please ensure Redis is running:")
        print("  brew services start redis    # macOS")
        print("  redis-server                  # Linux")
        return

    print("✅ Connected to Redis")

    # Step 2: Load separate F1M and F2M historical data
    print()
    print("Step 2/4: Loading dual-file historical data...")
    try:
        publisher.load_separate_files(
            f1m_csv=f1m_path,
            f2m_csv=f2m_path,
            f2m_window_days=f2m_window_days
        )
        print(f"✅ Loaded dual-file historical data")
        print(f"   F1M file: {f1m_path}")
        print(f"   F2M file: {f2m_path}")
        print(f"   F2M will be published during rollover window only ({f2m_window_days} days before expiration)")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        publisher.disconnect()
        return

    # Step 3: Create paper trading engine (playback mode)
    print()
    print("Step 3/4: Creating paper trading engine (playback mode)...")
    engine = RedisPaperTradingEngine(
        initial_capital=initial_capital,
        step=step,
        mode='playback',  # Playback mode uses abstract symbols
        redis_host='localhost',
        redis_port=6379,
        channel_prefix='market',
        contracts=['VN30F1M'],  # Abstract contract symbol
        f2m_window_days=f2m_window_days  # Subscribe to F2M within N days of expiration
    )
    print("✅ Engine created (mode: playback)")
    print(f"   Subscribed contracts: VN30F1M")
    print(f"   F2M window: {f2m_window_days} days before expiration")
    print(f"   F2M subscription: Conditional (during rollover only)")

    # Step 4: Start publishing and trading
    print()
    print("Step 4/4: Starting playback...")
    print("=" * 80)
    print()

    # Start dual-file publisher in background thread
    # Note: In production, avoid threading issues by using connection pooling
    def publish_data():
        try:
            publisher.start_publishing_dual(rate_hz=publish_rate_hz, loop=False)
        except Exception as e:
            print(f"⚠️  Publisher error: {e}")

    publisher_thread = threading.Thread(target=publish_data, daemon=True)
    publisher_thread.start()

    # Give publisher time to start
    time.sleep(0.5)

    # Run paper trading engine
    try:
        print(f"🚀 Running paper trading for {duration_seconds} seconds...")
        print()
        results = engine.run(duration_seconds=duration_seconds)

        # Wait for publisher to finish
        publisher_thread.join(timeout=5)

        # Display results
        print()
        print("=" * 80)
        print("📊 Trading Results Summary")
        print("=" * 80)
        print()

        if results:
            results.print_summary()

            # Additional insights
            print()
            print("📈 Performance Insights:")
            if results.messages_received > 0:
                throughput = results.messages_received / duration_seconds
                print(f"   Message Throughput: {throughput:.1f} msg/s")

                if throughput > 160:
                    print("   ✅ Exceeds target throughput (>160 msg/s)")
                else:
                    print(f"   ⚠️  Below target throughput (got {throughput:.1f}, target >160)")

            if results.avg_latency_ms is not None and results.avg_latency_ms > 0:
                if results.avg_latency_ms < 50:
                    print(f"   ✅ Low latency ({results.avg_latency_ms:.2f}ms < 50ms target)")
                else:
                    print(f"   ⚠️  High latency ({results.avg_latency_ms:.2f}ms > 50ms target)")

            if results.total_trades > 0:
                print(f"   💼 Trading Activity: {results.total_trades} trades executed")
                print(f"      • Buy trades: {results.buy_trades}")
                print(f"      • Sell trades: {results.sell_trades}")
            else:
                print("   ℹ️  No trades executed (market conditions or strategy parameters)")

            # Show F2M subscription status if available
            if hasattr(engine, 'redis_handler') and hasattr(engine.redis_handler, 'f2m_subscribed'):
                if engine.redis_handler.f2m_subscribed:
                    print("   📊 F2M Status: ACTIVE (within rollover window)")
                else:
                    print("   📊 F2M Status: INACTIVE (outside rollover window)")

            if results.rollovers and len(results.rollovers) > 0:
                print(f"   🔄 Contract Rollovers: {len(results.rollovers)}")
                for rollover in results.rollovers:
                    print(f"      • {rollover}")


        else:
            print("❌ No results available")

    except KeyboardInterrupt:
        print()
        print("⚠️  Interrupted by user")
        engine.stop()

    except Exception as e:
        print()
        print(f"❌ Error during trading: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        print()
        print("=" * 80)
        print("🧹 Cleanup")
        print("=" * 80)
        publisher.disconnect()
        print("✅ Disconnected from Redis")

    print()
    print("=" * 80)
    print("✅ Playback Mode Example Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()

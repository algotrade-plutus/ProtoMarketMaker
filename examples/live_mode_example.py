"""
Live Mode Example - Complete Demonstration

This example demonstrates running the paper trading engine in live mode with:
- Actual contract codes (VN30F2510, VN30F2511, etc.)
- Auto-detection of current front-month contract
- Manual contract mapping override
- Real-time market data processing simulation

Prerequisites:
- Redis server running on localhost:6379
- For real trading: Connect to live market data feed

Usage:
    # With auto-detection
    python examples/live_mode_example.py

    # With manual contract specification
    python examples/live_mode_example.py --contract VN30F2511
"""

import time
import argparse
from decimal import Decimal
from datetime import datetime

from tools.redis_publisher import RedisMarketDataPublisher
from paper_trading.engine import RedisPaperTradingEngine
from utils.contract_resolver import ContractSymbolResolver


def publish_simulated_live_data(publisher, contract_code, duration_seconds=60, rate_hz=10):
    """
    Simulate live market data publishing for demonstration purposes.

    In production, this would be replaced with actual market data feed.
    """
    print(f"📡 Publishing simulated market data for {contract_code}...")

    base_price = 1250.0
    message_count = 0
    end_time = time.time() + duration_seconds

    while time.time() < end_time:
        # Simulate price movement
        price_delta = (message_count % 10) - 5
        current_price = base_price + price_delta

        message_data = {
            'timestamp': datetime.now().isoformat(),
            'contract': contract_code,
            'price': current_price,
            'bid': current_price - 1.0,
            'ask': current_price + 1.0,
            'spread': 2.0,
            'volume': 100 + (message_count % 50)
        }

        publisher.publish_message(contract_code, message_data)
        message_count += 1

        # Control publish rate
        time.sleep(1.0 / rate_hz)

    print(f"✅ Published {message_count} simulated messages")


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Live Mode Paper Trading Example')
    parser.add_argument('--contract', type=str, help='Specific contract code (e.g., VN30F2511)')
    parser.add_argument('--duration', type=int, default=60, help='Duration in seconds (default: 60)')
    parser.add_argument('--capital', type=float, default=500000, help='Initial capital (default: 500000)')
    args = parser.parse_args()

    print("=" * 80)
    print("Live Mode Example - Paper Trading with Real Contract Codes")
    print("=" * 80)
    print()

    # Configuration
    initial_capital = Decimal(str(args.capital))
    step = Decimal('2.9')
    duration_seconds = args.duration
    publish_rate_hz = 10

    # Step 1: Contract Resolution
    print("Step 1/5: Contract Resolution...")
    resolver = ContractSymbolResolver()

    if args.contract:
        # Manual contract specification
        contract_code = args.contract
        print(f"✅ Using manually specified contract: {contract_code}")

        # Get contract details
        try:
            exp_date = resolver.get_expiration_date(contract_code)
            days_to_exp = resolver.get_days_to_expiration(contract_code)
            print(f"   Expiration Date: {exp_date}")
            print(f"   Days to Expiration: {days_to_exp}")

            if resolver.is_expiration_day(contract_code):
                print("   ⚠️  WARNING: Today is expiration day!")

        except Exception as e:
            print(f"   ⚠️  Could not parse contract details: {e}")
    else:
        # Auto-detection of front-month contract
        print("🔍 Auto-detecting current front-month contract...")
        contract_code = resolver.resolve('VN30F1M')
        f2m_code = resolver.resolve('VN30F2M')

        print(f"✅ Auto-detected contracts:")
        print(f"   F1M (Front Month): {contract_code}")
        print(f"   F2M (Second Month): {f2m_code}")

        # Get expiration details
        summary = resolver.get_resolution_summary(['VN30F1M', 'VN30F2M'])
        print()
        print("📅 Contract Details:")
        for symbol, info in summary.items():
            print(f"   {symbol}:")
            print(f"      Code: {info['code']}")
            print(f"      Expiration: {info['expiration']}")
            print(f"      Days to Expiry: {info['days_to_expiry']}")

    print()
    print("📋 Trading Configuration:")
    print(f"   Contract: {contract_code}")
    print(f"   Initial Capital: {initial_capital:,} VND")
    print(f"   Step Parameter: {step}")
    print(f"   Duration: {duration_seconds}s")
    print()

    # Step 2: Connect to Redis
    print("Step 2/5: Connecting to Redis...")
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

    # Step 3: Create paper trading engine (live mode)
    print()
    print("Step 3/5: Creating paper trading engine (live mode)...")
    engine = RedisPaperTradingEngine(
        initial_capital=initial_capital,
        step=step,
        mode='live',  # Live mode uses actual contract codes
        redis_host='localhost',
        redis_port=6379,
        channel_prefix='market',
        contracts=[contract_code]  # Actual contract code
    )
    print("✅ Engine created (mode: live)")
    print(f"   Subscribed to: {contract_code}")

    # Step 4: Start engine
    print()
    print("Step 4/5: Starting paper trading engine...")
    if not engine.start():
        print("❌ Failed to start engine")
        publisher.disconnect()
        return

    print("✅ Engine started")

    # Step 5: Simulate live data and monitor
    print()
    print("Step 5/5: Running live trading simulation...")
    print("=" * 80)
    print()

    try:
        # Publish simulated live data
        publish_simulated_live_data(
            publisher,
            contract_code,
            duration_seconds=duration_seconds,
            rate_hz=publish_rate_hz
        )

        # Give engine time to process final messages
        time.sleep(2)

        # Stop engine and get results
        print()
        print("🛑 Stopping engine...")
        results = engine.stop()

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

            if results.total_trades > 0:
                print(f"   💼 Trading Activity: {results.total_trades} trades executed")
                print(f"      • Buy trades: {results.buy_trades}")
                print(f"      • Sell trades: {results.sell_trades}")

                if results.final_nav != results.initial_capital:
                    pnl = results.final_nav - results.initial_capital
                    pnl_pct = (pnl / results.initial_capital) * 100

                    if pnl > 0:
                        print(f"   📈 P&L: +{pnl:,.2f} VND (+{pnl_pct:.2f}%)")
                    else:
                        print(f"   📉 P&L: {pnl:,.2f} VND ({pnl_pct:.2f}%)")
            else:
                print("   ℹ️  No trades executed")

            if results.reconnect_count > 0:
                print(f"   ⚠️  Redis reconnections: {results.reconnect_count}")

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
    print("✅ Live Mode Example Complete")
    print("=" * 80)
    print()
    print("💡 Next Steps:")
    print("   • Connect to actual market data feed for production use")
    print("   • Adjust strategy parameters (step, capital) as needed")
    print("   • Monitor performance and risk metrics")
    print("   • Review tests/integration/test_live_mode_e2e.py for more examples")


if __name__ == "__main__":
    main()

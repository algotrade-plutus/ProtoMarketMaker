"""
Paper Trading CLI Runner

Command-line interface for running Redis-based paper trading sessions
with contract symbol resolution and safety confirmation.
"""

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

from .engine import RedisPaperTradingEngine
from protomarketmaker.utils import ContractSymbolResolver


def confirm_contracts(resolver: ContractSymbolResolver, symbols: list) -> bool:
    """
    Display resolved symbols and ask for confirmation

    Args:
        resolver: ContractSymbolResolver instance
        symbols: List of informal symbols

    Returns:
        True if user confirms, False otherwise
    """
    print()
    print("🔍 Contract Symbol Resolution:")

    summary = resolver.get_resolution_summary(symbols)
    for informal, info in summary.items():
        code = info['code']
        expiration = info['expiration']
        days = info['days_to_expiry']

        expiry_str = expiration.strftime('%b %d, %Y')
        print(f"   {informal} → {code} (expires {expiry_str}, {days} days)")

    print()
    print("⚠️  Please verify ticker symbols are correct.")
    response = input("Proceed with trading? [Y/n]: ").strip().lower()

    return response in ['y', 'yes', '']


def load_config():
    """Load Redis config from file or return defaults"""
    config_path = Path('config/redis_config.json')

    if config_path.exists():
        import json
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Default configuration
        return {
            "redis_host": "localhost",
            "redis_port": 6379,
            "channel_prefix": "market",
            "contracts": ["VN30F1M"],
            "auto_detect_contracts": True,
            "confirm_symbols": True,
            "initial_capital": 500000,
            "step": 2.9,
            "update_interval_seconds": 15,
            "record_events": False,
            "event_log_path": "logs/paper_trading/events.jsonl"
        }


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Redis-Based Paper Trading Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Playback mode (testing with historical data, default)
  python -m paper_trading.runner --mode playback --contracts VN30F1M

  # Time-limited playback session (1 hour)
  python -m paper_trading.runner --mode playback --duration 3600 --output results/session.json

  # Live mode (production trading with actual contract codes)
  python -m paper_trading.runner --mode live --contracts VN30F2510 --redis-host 192.168.1.100

  # Custom F2M subscription window (5 days before expiration)
  python -m paper_trading.runner --mode playback --f2m-window-days 5

  # With event recording for debugging
  python -m paper_trading.runner --record-events --event-log logs/debug.jsonl

  # Disable confirmation for automation
  python -m paper_trading.runner --no-confirm
        """
    )

    # Configuration source
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        '--config',
        type=str,
        default='config/redis_config.json',
        help='Path to Redis config JSON file (default: config/redis_config.json)'
    )

    # Redis connection (overrides config file)
    redis_group = parser.add_argument_group('Redis Connection')
    redis_group.add_argument(
        '--redis-host',
        type=str,
        help='Redis server hostname (overrides config)'
    )
    redis_group.add_argument(
        '--redis-port',
        type=int,
        help='Redis server port (overrides config)'
    )
    redis_group.add_argument(
        '--channel-prefix',
        type=str,
        help='Redis channel prefix (overrides config)'
    )

    # Trading parameters
    trading_group = parser.add_argument_group('Trading Parameters')
    trading_group.add_argument(
        '--mode',
        type=str,
        choices=['playback', 'live'],
        help='Operating mode: "playback" (testing with historical data) or "live" (production trading)'
    )
    trading_group.add_argument(
        '--contracts',
        nargs='+',
        help='List of contracts to trade (e.g., VN30F1M for playback, VN30F2510 for live)'
    )
    trading_group.add_argument(
        '--capital',
        type=float,
        help='Initial capital (overrides config)'
    )
    trading_group.add_argument(
        '--step',
        type=float,
        help='Strategy step parameter (overrides config)'
    )
    trading_group.add_argument(
        '--update-interval',
        type=int,
        help='Signal update interval in seconds (overrides config)'
    )
    trading_group.add_argument(
        '--f2m-window-days',
        type=int,
        help='Days before expiration to subscribe to F2M contract (default: 3)'
    )

    # Session control
    session_group = parser.add_argument_group('Session Control')
    session_group.add_argument(
        '--duration',
        type=int,
        help='Session duration in seconds (None = indefinite, Ctrl+C to stop)'
    )
    session_group.add_argument(
        '--output',
        type=str,
        help='Output JSON file for results (default: print to console only)'
    )
    session_group.add_argument(
        '--no-confirm',
        action='store_true',
        help='Disable contract symbol confirmation prompt'
    )

    # Event recording
    recording_group = parser.add_argument_group('Event Recording')
    recording_group.add_argument(
        '--record-events',
        action='store_true',
        help='Enable event recording to JSONL for debugging'
    )
    recording_group.add_argument(
        '--event-log',
        type=str,
        help='Path to event log file (default: logs/paper_trading/events.jsonl)'
    )

    # Audit logging
    audit_group = parser.add_argument_group('Audit Logging')
    audit_group.add_argument(
        '--audit-log',
        action='store_true',
        help='Enable audit logging (signals, fills, rollovers)'
    )
    audit_group.add_argument(
        '--audit-log-path',
        type=str,
        help='Path to audit log file (default: logs/audit/session_<timestamp>.log)'
    )

    # Logging configuration
    logging_group = parser.add_argument_group('Logging')
    logging_group.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='WARNING',
        help='Set logging level (default: WARNING)'
    )

    args = parser.parse_args()

    # Configure logging based on --log-level
    numeric_level = getattr(logging, args.log_level.upper(), logging.WARNING)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Load config from file
    config = load_config()

    # Override with command-line arguments
    redis_host = args.redis_host or config.get('redis_host', 'localhost')
    redis_port = args.redis_port or config.get('redis_port', 6379)
    channel_prefix = args.channel_prefix or config.get('channel_prefix', 'market')
    mode = args.mode or config.get('mode', 'playback')
    contracts = args.contracts or config.get('contracts', ['VN30F1M'] if mode == 'playback' else ['VN30F2510'])
    capital = Decimal(str(args.capital)) if args.capital else Decimal(str(config.get('initial_capital', 500000)))
    step = Decimal(str(args.step)) if args.step else Decimal(str(config.get('step', 2.9)))
    update_interval = args.update_interval or config.get('update_interval_seconds', 15)
    f2m_window_days = args.f2m_window_days or config.get('f2m_window_days', 3)

    # Event recording settings
    record_events = args.record_events or config.get('record_events', False)
    event_log_path = args.event_log or config.get('event_log_path', 'logs/paper_trading/events.jsonl')

    # Audit logging settings
    audit_log_enabled = args.audit_log or config.get('audit_log', False)
    if audit_log_enabled and not args.audit_log_path:
        # Generate default audit log path with timestamp
        from datetime import datetime as dt
        timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
        audit_log_path = f'logs/audit/session_{timestamp}.log'
    else:
        audit_log_path = args.audit_log_path or config.get('audit_log_path', None)

    # Contract resolution settings
    auto_detect = config.get('auto_detect_contracts', True)
    confirm_symbols = config.get('confirm_symbols', True) and not args.no_confirm
    manual_mappings = config.get('contract_mappings', {})

    # Contract resolution (only for live mode)
    if mode == 'live':
        # Live mode: Resolve abstract symbols to actual contract codes
        if auto_detect:
            resolver = ContractSymbolResolver()
        else:
            resolver = ContractSymbolResolver(manual_mappings=manual_mappings)

        # Resolve contracts
        resolved_contracts = resolver.resolve_all(contracts)
    else:
        # Playback mode: Use abstract symbols directly (VN30F1M, VN30F2M)
        # No resolution needed - abstract symbols are used as-is
        resolved_contracts = contracts
        resolver = None  # No resolver needed for playback mode

    # Print configuration
    print("=" * 60)
    print("REDIS PAPER TRADING SESSION")
    print("=" * 60)
    print(f"Mode:      {mode}")
    print(f"Redis:     {redis_host}:{redis_port}")
    print(f"Contracts: {', '.join(contracts)}")
    print(f"Capital:   {capital:,.2f} VND")
    print(f"Step:      {step}")
    print(f"Interval:  {update_interval}s")
    print(f"F2M Window: {f2m_window_days} days")
    if record_events:
        print(f"Recording: {event_log_path}")
    if audit_log_enabled:
        print(f"Audit Log: {audit_log_path}")
    print("=" * 60)

    # Contract symbol resolution and confirmation (live mode only)
    if mode == 'live':
        if confirm_symbols:
            if not confirm_contracts(resolver, contracts):
                print("\nTrading cancelled by user.")
                return 0
        else:
            # Show resolution without confirmation
            print()
            print("🔍 Contract Symbol Resolution (auto-confirmed):")
            summary = resolver.get_resolution_summary(contracts)
            for informal, info in summary.items():
                print(f"   {informal} → {info['code']}")
            print()
    else:
        # Playback mode: Display abstract symbols used
        print()
        print("📋 Playback Mode - Abstract Symbols:")
        for contract in contracts:
            print(f"   {contract} (abstract symbol, no resolution)")
        print()

    # Initialize engine
    try:
        engine = RedisPaperTradingEngine(
            initial_capital=capital,
            step=step,
            redis_host=redis_host,
            redis_port=redis_port,
            channel_prefix=channel_prefix,
            contracts=resolved_contracts,  # Use resolved contract codes, not informal symbols
            update_interval_seconds=update_interval,
            record_events=record_events,
            event_log_path=event_log_path,
            mode=mode,
            f2m_window_days=f2m_window_days,
            audit_log_enabled=audit_log_enabled,
            audit_log_path=audit_log_path
        )
    except Exception as e:
        print(f"Error initializing engine: {e}", file=sys.stderr)
        return 1

    # Run trading session
    try:
        results = engine.run(duration_seconds=args.duration)

        if results is None:
            print("Session ended without results", file=sys.stderr)
            return 1

        # Print summary
        results.print_summary()

        # Export to file if requested
        if args.output:
            results.to_json(args.output)
            print(f"\nResults exported to: {args.output}")

        return 0

    except Exception as e:
        print(f"Error during trading session: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

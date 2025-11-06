"""
Simple CLI Runner for Event-Driven Backtesting

Runs backtests and compares with original backtesting.py results.
"""
import argparse
from decimal import Decimal
from datetime import date
import logging
import sys

from .engine import BacktestingEngine


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Event-Driven Backtesting Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in-sample backtest
  python -m backtesting.runner \\
    --csv data/is/historical.csv \\
    --start 2022-01-01 \\
    --end 2023-01-01 \\
    --capital 500000 \\
    --step 2.9

  # Run out-of-sample
  python -m backtesting.runner \\
    --csv data/os/historical.csv \\
    --start 2024-01-02 \\
    --end 2025-04-29 \\
    --capital 500000 \\
    --step 2.9

  # Save results to JSON
  python -m backtesting.runner \\
    --csv data/is/historical.csv \\
    --start 2022-01-01 \\
    --end 2023-01-01 \\
    --capital 500000 \\
    --step 2.9 \\
    --output results/backtest_results.json
        """
    )

    # Required arguments
    parser.add_argument('--csv', required=True, help='Path to CSV file')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')

    # Optional arguments
    parser.add_argument('--capital', type=float, default=500000.0,
                        help='Initial capital (default: 500000)')
    parser.add_argument('--step', type=float, default=2.9,
                        help='Strategy step parameter (default: 2.9)')
    parser.add_argument('--interval', type=int, default=15,
                        help='Update interval seconds (default: 15)')
    parser.add_argument('--fee', type=float, default=20.0,
                        help='Fee per contract (default: 20.0)')

    # Output options
    parser.add_argument('--output', help='Save results to JSON file')
    parser.add_argument('--no-progress', action='store_true',
                        help='Disable progress bar')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    try:
        # Parse dates
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)

        # Create engine
        logger.info("Initializing backtesting engine...")
        engine = BacktestingEngine(
            initial_capital=Decimal(str(args.capital)),
            step=Decimal(str(args.step)),
            csv_path=args.csv,
            update_interval_seconds=args.interval,
            fee_per_contract=Decimal(str(args.fee))
        )

        # Run backtest
        logger.info(f"Running backtest from {start_date} to {end_date}...")
        results = engine.run(
            start_date=start_date,
            end_date=end_date,
            show_progress=not args.no_progress
        )

        # Print results
        print("\n" + "="*60)
        print(results.summary())
        print("="*60 + "\n")

        # Save to file if requested
        if args.output:
            results.to_json(args.output)
            logger.info(f"Results saved to {args.output}")

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid value: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())

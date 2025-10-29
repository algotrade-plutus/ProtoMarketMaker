"""
Paper Trading CLI

Command-line interface for running paper trading sessions.
"""
import argparse
import json
from decimal import Decimal
from datetime import datetime
import pandas as pd
import logging
from pathlib import Path

from paper_trading.session import TradingSession


def setup_logging(level: str = "INFO", log_dir: str = "logs/paper_trading"):
    """
    Configure logging

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    log_file = f"{log_dir}/session_{datetime.now():%Y%m%d_%H%M%S}.log"

    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    return log_file


def load_data(filepath: str) -> pd.DataFrame:
    """
    Load historical data from CSV

    Args:
        filepath: Path to CSV file

    Returns:
        DataFrame with market data
    """
    df = pd.read_csv(filepath)

    # Convert datetime column
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])

    return df


def save_results(summary: dict, output_path: str):
    """
    Save session summary to JSON file

    Args:
        summary: Session summary dictionary
        output_path: Path to output file
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Convert Decimal to float for JSON serialization
    def decimal_to_float(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError

    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2, default=decimal_to_float)


def print_summary(summary: dict):
    """
    Print formatted summary to console

    Args:
        summary: Session summary dictionary
    """
    print("\n" + "="*70)
    print("PAPER TRADING SESSION SUMMARY")
    print("="*70)

    # Portfolio summary
    portfolio = summary['portfolio']
    print(f"\n{'Portfolio':<30} {'Value':<20}")
    print("-" * 50)
    print(f"{'Initial Capital:':<30} {portfolio['initial_capital']:>20,.2f}")
    print(f"{'Final NAV:':<30} {portfolio['final_nav']:>20,.2f}")
    print(f"{'Cash:':<30} {portfolio['cash']:>20,.2f}")
    print(f"{'Total Return:':<30} {portfolio['total_return']:>19,.2f}%")

    # Positions
    if portfolio['positions']:
        print(f"\n{'Positions':<30}")
        print("-" * 50)
        for pos in portfolio['positions']:
            print(f"  {pos['contract']:<10} qty={pos['quantity']:>5} "
                  f"avg_px={pos['average_price']:>10.1f} "
                  f"pnl={pos['total_pnl']:>10.2f}")

    # Orders summary
    orders = summary['orders']
    print(f"\n{'Orders':<30} {'Value':<20}")
    print("-" * 50)
    print(f"{'Total Orders:':<30} {orders['total_orders']:>20}")
    print(f"{'Filled Orders:':<30} {orders['filled_orders']:>20}")
    print(f"{'Cancelled Orders:':<30} {orders['cancelled_orders']:>20}")
    print(f"{'Active Orders:':<30} {orders['active_orders']:>20}")

    # Performance metrics
    if summary['performance']:
        perf = summary['performance']
        print(f"\n{'Performance Metrics':<30}")
        print("-" * 50)

        if 'sharpe_ratio' in perf:
            print(f"{'Sharpe Ratio:':<30} {perf['sharpe_ratio']:>20.4f}")
        if 'sortino_ratio' in perf:
            print(f"{'Sortino Ratio:':<30} {perf['sortino_ratio']:>20.4f}")
        if 'maximum_drawdown' in perf:
            print(f"{'Maximum Drawdown:':<30} {perf['maximum_drawdown']:>19.2f}%")
        if 'volatility' in perf:
            print(f"{'Volatility (Annual):':<30} {perf['volatility']:>19.2f}%")

    print("="*70)
    print()


def main():
    """Main entry point for paper trading CLI"""
    parser = argparse.ArgumentParser(
        description='Paper Trading System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run backtest with default parameters
  python -m paper_trading.main --data data/historical.csv

  # Run with custom capital and step
  python -m paper_trading.main --data data/historical.csv --capital 1000000 --step 3.5

  # Run with debug logging
  python -m paper_trading.main --data data/historical.csv --log-level DEBUG
        """
    )

    parser.add_argument('--data', required=True, help='Path to CSV data file')
    parser.add_argument('--capital', type=float, default=500000,
                        help='Initial capital (default: 500000)')
    parser.add_argument('--step', type=float, default=2.9,
                        help='Strategy step parameter (default: 2.9)')
    parser.add_argument('--interval', type=int, default=15,
                        help='Update interval in seconds (default: 15)')
    parser.add_argument('--output', default='result/paper_trading/summary.json',
                        help='Output file for results (default: result/paper_trading/summary.json)')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level (default: INFO)')
    parser.add_argument('--log-dir', default='logs/paper_trading',
                        help='Directory for log files (default: logs/paper_trading)')

    args = parser.parse_args()

    # Setup logging
    log_file = setup_logging(args.log_level, args.log_dir)
    logger = logging.getLogger(__name__)

    try:
        # Load data
        logger.info(f"Loading data from {args.data}")
        data = load_data(args.data)
        logger.info(f"Loaded {len(data)} rows of data")

        # Create session
        logger.info("Creating trading session")
        session = TradingSession(
            initial_capital=Decimal(str(args.capital)),
            step=Decimal(str(args.step)),
            update_interval_seconds=args.interval
        )

        # Run backtest
        logger.info("Running backtest...")
        summary = session.run_backtest(data)

        # Save results
        logger.info(f"Saving results to {args.output}")
        save_results(summary, args.output)

        # Print summary
        print_summary(summary)

        logger.info(f"Session complete. Log file: {log_file}")
        logger.info(f"Results saved to: {args.output}")

    except Exception as e:
        logger.error(f"Error during session: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())

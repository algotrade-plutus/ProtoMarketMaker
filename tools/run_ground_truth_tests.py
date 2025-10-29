"""
Run Ground Truth Tests

Runs iterative backtest on all sample data sizes and generates comprehensive logs
for establishing ground truth behavior.

Usage:
    python tools/run_ground_truth_tests.py
"""
import sys
from decimal import Decimal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from iterative_backtesting import Backtesting

# Test configurations
TESTS = [
    {
        'name': '1day',
        'description': 'Single day mid-month (Feb 7)',
        'step': Decimal('2.9')
    },
    {
        'name': '2day',
        'description': 'Two consecutive days (Feb 7-8)',
        'step': Decimal('2.9')
    },
    {
        'name': '3day',
        'description': 'Three days (Feb 7-9)',
        'step': Decimal('2.9')
    },
    {
        'name': '1week',
        'description': 'One week without rollover (Feb 7-11)',
        'step': Decimal('2.9')
    },
    {
        'name': '1week_rollover',
        'description': 'One week WITH ROLLOVER (Feb 14-18, exp Feb 17)',
        'step': Decimal('2.9')
    },
    {
        'name': '1month',
        'description': 'One month with one rollover (Feb 7 - Mar 7)',
        'step': Decimal('2.9')
    },
    {
        'name': '2month',
        'description': 'Two months with two rollovers (Feb 7 - Apr 8)',
        'step': Decimal('2.9')
    }
]

def load_sample_data(sample_name: str):
    """
    Load pre-merged sample data from data/sample/

    These samples are sliced from merged_is_data.csv which already has
    ffill() applied on the full dataset, eliminating boundary issues that
    occur when merging separate F1M/F2M files for limited date ranges.

    Benefits of this approach:
    - No NaN boundary issues (ffill already done on full dataset)
    - Exact match to what original backtest sees for these dates
    - F2M prices correctly propagated to all rows
    - Simpler code (no merge logic needed)

    Reference: internal-docs/ground-truth-data-preparation.md
    """
    import pandas as pd

    # Load pre-merged sample
    data = pd.read_csv(f'data/sample/merged_is_data_{sample_name}.csv')

    # Convert datetime columns
    data['datetime'] = pd.to_datetime(data['datetime'])
    data['date'] = pd.to_datetime(data['date']).dt.date

    # Convert price columns to Decimal with 2 decimal precision
    # Original strategy uses Decimal("0.0") for bid/ask quantize (1 decimal place)
    # Using 2 decimals provides safe buffer for rounding
    #
    # IMPORTANT: f2_price must also be Decimal. Even though ffill() is called in
    # the original process_data(), pandas keeps Decimal objects in object dtype.
    # Only after CSV serialization does it become float64.
    decimal_columns = ['price', 'close', 'best-bid', 'best-ask', 'spread', 'f2_close', 'f2_price']
    for col in decimal_columns:
        data[col] = data[col].apply(
            lambda x: Decimal(str(round(float(x), 2))) if pd.notna(x) else None
        )

    return data

def run_test(test_config):
    """Run a single ground truth test"""
    name = test_config['name']
    description = test_config['description']
    step = test_config['step']

    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"{'='*80}")
    print(f"Description: {description}")
    print(f"Step: {step}")

    # Load data
    print("Loading data...")
    data = load_sample_data(name)
    print(f"  Rows: {len(data):,}")
    print(f"  Date range: {data['date'].min()} to {data['date'].max()}")
    print(f"  Trading days: {data['date'].nunique()}")

    # Run backtest with logging
    log_path = f'logs/ground_truth/iterative_{name}.log'
    print(f"Running backtest...")
    print(f"  Log file: {log_path}")

    bt = Backtesting(capital=Decimal('500000'), printable=False)
    bt.run(data, step, log_path=log_path)

    # Report results
    print(f"\nResults:")
    print(f"  Final NAV: {bt.daily_assets[-1]:,.2f}")
    print(f"  HPR: {(bt.daily_assets[-1] / bt.daily_assets[0] - 1) * 100:.2f}%")
    print(f"  Total signals: {bt.signal_count}")
    print(f"  Total fills: {bt.fill_count}")
    print(f"  Total force sells: {bt.force_sell_count}")
    print(f"  Total rollovers: {bt.rollover_count}")
    print(f"  Final inventory: {bt.inventory}")

    sharpe = None
    if bt.metric:
        try:
            sharpe = bt.metric.sharpe_ratio(Decimal('0.00023'))
            print(f"  Sharpe Ratio: {sharpe:.4f}")
        except Exception as e:
            print(f"  Sharpe Ratio: N/A (insufficient data: {e})")

    print(f"✅ Test complete")

    return {
        'name': name,
        'nav': bt.daily_assets[-1],
        'hpr': (bt.daily_assets[-1] / bt.daily_assets[0] - 1) * 100,
        'signals': bt.signal_count,
        'fills': bt.fill_count,
        'force_sells': bt.force_sell_count,
        'rollovers': bt.rollover_count,
        'inventory': bt.inventory,
        'sharpe': sharpe
    }

def main():
    print("="*80)
    print("GROUND TRUTH TEST SUITE")
    print("="*80)
    print("\nRunning iterative backtest on all sample data sets...")
    print("This will establish ground truth for event-driven comparison.\n")

    # Create log directory
    import os
    os.makedirs('logs/ground_truth', exist_ok=True)
    print("✅ Created logs/ground_truth/ directory\n")

    # Run all tests
    results = []
    for test in TESTS:
        try:
            result = run_test(test)
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'name': test['name'],
                'error': str(e)
            })

    # Generate summary report
    print(f"\n{'='*80}")
    print("SUMMARY REPORT")
    print(f"{'='*80}\n")

    summary_path = 'logs/ground_truth/summary_report.txt'
    with open(summary_path, 'w') as f:
        f.write("GROUND TRUTH TEST SUMMARY\n")
        f.write("="*80 + "\n\n")

        f.write(f"{'Test':<20} {'NAV':<15} {'HPR':<10} {'Signals':<10} {'Fills':<8} {'Rollovers':<12} {'Inventory':<10}\n")
        f.write("-"*80 + "\n")

        for result in results:
            if 'error' in result:
                f.write(f"{result['name']:<20} ERROR: {result['error']}\n")
                print(f"{result['name']:<20} ERROR")
            else:
                f.write(
                    f"{result['name']:<20} {result['nav']:<15,.2f} {result['hpr']:<10.2f} "
                    f"{result['signals']:<10} {result['fills']:<8} {result['rollovers']:<12} {result['inventory']:<10}\n"
                )
                print(
                    f"{result['name']:<20} NAV={result['nav']:,.2f} | "
                    f"Signals={result['signals']} | Fills={result['fills']} | "
                    f"Rollovers={result['rollovers']}"
                )

        f.write("\n" + "="*80 + "\n")
        f.write("All logs saved to logs/ground_truth/\n")

    print(f"\n✅ Summary report saved to: {summary_path}")
    print(f"✅ All test logs saved to: logs/ground_truth/")
    print(f"\nGround truth establishment complete!")

if __name__ == "__main__":
    main()

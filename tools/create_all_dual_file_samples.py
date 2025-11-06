"""
Create all dual-file F1M/F2M samples matching the merged data test cases

This script creates separate F1M and F2M CSV files for each test case:
- 1day (Feb 7, 2022)
- 2day (Feb 7-8, 2022)
- 3day (Feb 7-9, 2022)
- 1week (Feb 7-11, 2022)
- 1week_rollover (Feb 14-18, 2022)
- 1month (Feb 7 - Mar 7, 2022)
- 2month (Feb 7 - Apr 8, 2022)

Usage:
    python tools/create_all_dual_file_samples.py
"""
import pandas as pd
from pathlib import Path
from datetime import datetime


# Define all sample date ranges
SAMPLE_CONFIGS = [
    {
        'name': '1day',
        'start_date': '2022-02-07',
        'end_date': '2022-02-07',
        'description': 'Single day (Feb 7) - no rollover'
    },
    {
        'name': '2day',
        'start_date': '2022-02-07',
        'end_date': '2022-02-08',
        'description': 'Two days (Feb 7-8) - no rollover'
    },
    {
        'name': '3day',
        'start_date': '2022-02-07',
        'end_date': '2022-02-09',
        'description': 'Three days (Feb 7-9) - no rollover'
    },
    {
        'name': '1week',
        'start_date': '2022-02-07',
        'end_date': '2022-02-11',
        'description': 'One week (Feb 7-11) - no rollover'
    },
    {
        'name': '1week_rollover',
        'start_date': '2022-02-14',
        'end_date': '2022-02-18',
        'description': 'One week (Feb 14-18) - WITH rollover on Feb 17'
    },
    {
        'name': '1month',
        'start_date': '2022-02-07',
        'end_date': '2022-03-07',
        'description': 'One month (Feb 7 - Mar 7) - WITH rollover on Feb 17'
    },
    {
        'name': '2month',
        'start_date': '2022-02-07',
        'end_date': '2022-04-08',
        'description': 'Two months (Feb 7 - Apr 8) - WITH 2 rollovers (Feb 17, Mar 17)'
    }
]


def create_dual_file_sample(config: dict, f1m_df: pd.DataFrame, f2m_df: pd.DataFrame, output_dir: Path):
    """
    Create a dual-file sample for a specific date range

    Args:
        config: Sample configuration dict with name, start_date, end_date
        f1m_df: Full F1M dataframe
        f2m_df: Full F2M dataframe
        output_dir: Output directory for sample files
    """
    name = config['name']
    start_date = config['start_date']
    end_date = config['end_date']
    description = config['description']

    print(f"\n{'=' * 80}")
    print(f"Creating sample: {name}")
    print(f"Description: {description}")
    print(f"Date range: {start_date} to {end_date}")
    print('=' * 80)

    # Filter by date range
    f1m_filtered = f1m_df[
        (f1m_df['date'] >= start_date) &
        (f1m_df['date'] <= end_date)
    ].copy()

    f2m_filtered = f2m_df[
        (f2m_df['date'] >= start_date) &
        (f2m_df['date'] <= end_date)
    ].copy()

    # Output files
    f1m_output = output_dir / f'VN30F1M_{name}.csv'
    f2m_output = output_dir / f'VN30F2M_{name}.csv'

    # Save files
    print(f"\nSaving F1M sample ({len(f1m_filtered):,} rows) to {f1m_output}...")
    f1m_filtered.to_csv(f1m_output, index=False)

    print(f"Saving F2M sample ({len(f2m_filtered):,} rows) to {f2m_output}...")
    f2m_filtered.to_csv(f2m_output, index=False)

    # Calculate file sizes
    f1m_size = f1m_output.stat().st_size / 1024  # KB
    f2m_size = f2m_output.stat().st_size / 1024  # KB

    # Print summary
    print(f"\n✅ F1M sample created:")
    print(f"   File: {f1m_output.name}")
    print(f"   Size: {f1m_size:.1f} KB")
    print(f"   Rows: {len(f1m_filtered):,}")
    if len(f1m_filtered) > 0:
        print(f"   Date range: {f1m_filtered['date'].min()} to {f1m_filtered['date'].max()}")
        print(f"   Contracts: {f1m_filtered['tickersymbol'].unique().tolist()}")

    print(f"\n✅ F2M sample created:")
    print(f"   File: {f2m_output.name}")
    print(f"   Size: {f2m_size:.1f} KB")
    print(f"   Rows: {len(f2m_filtered):,}")
    if len(f2m_filtered) > 0:
        print(f"   Date range: {f2m_filtered['date'].min()} to {f2m_filtered['date'].max()}")
        print(f"   Contracts: {f2m_filtered['tickersymbol'].unique().tolist()}")

    return {
        'name': name,
        'f1m_file': f1m_output.name,
        'f1m_rows': len(f1m_filtered),
        'f1m_size_kb': f1m_size,
        'f2m_file': f2m_output.name,
        'f2m_rows': len(f2m_filtered),
        'f2m_size_kb': f2m_size,
        'description': description
    }


def main():
    """Create all dual-file samples"""
    print("=" * 80)
    print("CREATE ALL DUAL-FILE F1M/F2M SAMPLES")
    print("=" * 80)

    # Input paths
    f1m_input = Path('data/is/VN30F1M_data.csv')
    f2m_input = Path('data/is/VN30F2M_data.csv')

    # Output directory
    output_dir = Path('data/sample')
    output_dir.mkdir(parents=True, exist_ok=True)

    # Verify input files exist
    if not f1m_input.exists():
        print(f"❌ Error: F1M data not found at {f1m_input}")
        print("Please ensure the F1M data file exists")
        return

    if not f2m_input.exists():
        print(f"❌ Error: F2M data not found at {f2m_input}")
        print("Please ensure the F2M data file exists")
        return

    # Load full datasets
    print(f"\nLoading F1M data from {f1m_input}...")
    print(f"  File size: {f1m_input.stat().st_size / 1024 / 1024:.1f} MB")
    f1m_df = pd.read_csv(f1m_input, parse_dates=['datetime', 'date'])
    print(f"  Loaded {len(f1m_df):,} rows")
    print(f"  Date range: {f1m_df['date'].min()} to {f1m_df['date'].max()}")

    print(f"\nLoading F2M data from {f2m_input}...")
    print(f"  File size: {f2m_input.stat().st_size / 1024 / 1024:.1f} MB")
    f2m_df = pd.read_csv(f2m_input, parse_dates=['datetime', 'date'])
    print(f"  Loaded {len(f2m_df):,} rows")
    print(f"  Date range: {f2m_df['date'].min()} to {f2m_df['date'].max()}")

    # Create all samples
    results = []
    for config in SAMPLE_CONFIGS:
        result = create_dual_file_sample(config, f1m_df, f2m_df, output_dir)
        results.append(result)

    # Print final summary
    print("\n" + "=" * 80)
    print("SUMMARY - ALL DUAL-FILE SAMPLES CREATED")
    print("=" * 80)
    print(f"\nOutput directory: {output_dir}/")
    print(f"\nTotal samples: {len(results)}")

    print("\n| Sample | F1M File | F1M Rows | F2M File | F2M Rows | Description |")
    print("|--------|----------|----------|----------|----------|-------------|")
    for r in results:
        print(f"| {r['name']} | {r['f1m_file']} | {r['f1m_rows']:,} | {r['f2m_file']} | {r['f2m_rows']:,} | {r['description']} |")

    # Calculate total sizes
    total_f1m_size = sum(r['f1m_size_kb'] for r in results)
    total_f2m_size = sum(r['f2m_size_kb'] for r in results)

    print(f"\nTotal F1M data: {total_f1m_size / 1024:.1f} MB ({len(results)} files)")
    print(f"Total F2M data: {total_f2m_size / 1024:.1f} MB ({len(results)} files)")
    print(f"Grand total: {(total_f1m_size + total_f2m_size) / 1024:.1f} MB ({len(results) * 2} files)")

    print("\n" + "=" * 80)
    print("✅ ALL DUAL-FILE SAMPLES CREATED SUCCESSFULLY")
    print("=" * 80)

    print("\n💡 Usage Examples:")
    print("   # Playback mode with 1-day sample")
    print("   python -m paper_trading.runner --mode playback --f1m-csv data/sample/VN30F1M_1day.csv --f2m-csv data/sample/VN30F2M_1day.csv")
    print()
    print("   # Playback mode with 1-month sample (includes rollover)")
    print("   python -m paper_trading.runner --mode playback --f1m-csv data/sample/VN30F1M_1month.csv --f2m-csv data/sample/VN30F2M_1month.csv")


if __name__ == '__main__':
    main()

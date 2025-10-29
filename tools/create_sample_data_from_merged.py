"""
Extract sample periods from merged_is_data.csv for ground truth testing.

This approach ensures:
1. No ffill boundary issues (data already ffilled on full dataset)
2. Exact match to what original backtest sees for these dates
3. F2M prices properly propagated to all rows

The samples are sliced from data/is/merged_is_data.csv which was produced by
the original process_data() function with merge and ffill already applied.

Reference: internal-docs/ground-truth-data-preparation.md
"""

import pandas as pd
from datetime import date
import os

# Sample configurations
SAMPLES = {
    '1day': {
        'start': date(2022, 2, 7),
        'end': date(2022, 2, 7),
        'description': 'Single day mid-month (Feb 7)'
    },
    '2day': {
        'start': date(2022, 2, 7),
        'end': date(2022, 2, 8),
        'description': 'Two consecutive days (Feb 7-8)'
    },
    '3day': {
        'start': date(2022, 2, 7),
        'end': date(2022, 2, 9),
        'description': 'Three days (Feb 7-9)'
    },
    '1week': {
        'start': date(2022, 2, 7),
        'end': date(2022, 2, 11),
        'description': 'One week without rollover (Feb 7-11)'
    },
    '1week_rollover': {
        'start': date(2022, 2, 14),
        'end': date(2022, 2, 18),
        'description': 'One week WITH ROLLOVER (Feb 14-18, expiration Feb 17)'
    },
    '1month': {
        'start': date(2022, 2, 7),
        'end': date(2022, 3, 7),
        'description': 'One month with one rollover (Feb 7 - Mar 7)'
    },
    '2month': {
        'start': date(2022, 2, 7),
        'end': date(2022, 4, 8),
        'description': 'Two months with two rollovers (Feb 7 - Apr 8)'
    }
}

def extract_samples():
    """Extract sample periods from merged_is_data.csv"""

    print("=" * 80)
    print("EXTRACTING SAMPLE DATA FROM MERGED SOURCE")
    print("=" * 80)
    print()

    # Load full merged data
    input_path = 'data/is/merged_is_data.csv'
    print(f"Loading {input_path}...")

    if not os.path.exists(input_path):
        print(f"❌ Error: {input_path} not found!")
        print("   Please ensure merged_is_data.csv exists in data/is/")
        return

    data = pd.read_csv(input_path)
    print(f"  ✓ Loaded {len(data):,} rows")

    # Convert date column for filtering
    data['date'] = pd.to_datetime(data['date']).dt.date

    print(f"  ✓ Date range: {data['date'].min()} to {data['date'].max()}")
    print()

    # Create output directory if needed
    os.makedirs('data/sample', exist_ok=True)

    # Extract each sample
    print("Extracting samples:")
    print("-" * 80)

    total_size = 0
    for name, config in SAMPLES.items():
        # Filter by date range (inclusive)
        mask = (data['date'] >= config['start']) & (data['date'] <= config['end'])
        sample = data[mask].copy()

        if len(sample) == 0:
            print(f"⚠️  {name:20s}: No data found for date range!")
            continue

        # Save to CSV
        output_path = f'data/sample/merged_is_data_{name}.csv'
        sample.to_csv(output_path, index=False)

        # Get file size
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        total_size += file_size_mb

        # Get statistics
        num_days = sample['date'].nunique()
        date_min = sample['date'].min()
        date_max = sample['date'].max()

        # Check for rollovers (Feb 17, Mar 17 are 3rd Thursdays)
        rollover_dates = [date(2022, 2, 17), date(2022, 3, 17)]
        has_rollover = any(d in sample['date'].values for d in rollover_dates)
        rollover_str = " (includes rollover)" if has_rollover else ""

        print(f"✓ {name:20s}: {len(sample):>7,} rows | {num_days:>2} days | "
              f"{date_min} to {date_max} | {file_size_mb:>5.1f} MB{rollover_str}")

    print("-" * 80)
    print(f"Total: {total_size:.1f} MB in {len(SAMPLES)} sample files")
    print()
    print("=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print()
    print("Sample files created in: data/sample/")
    print("  merged_is_data_1day.csv")
    print("  merged_is_data_2day.csv")
    print("  merged_is_data_3day.csv")
    print("  merged_is_data_1week.csv")
    print("  merged_is_data_1week_rollover.csv")
    print("  merged_is_data_1month.csv")
    print("  merged_is_data_2month.csv")
    print()
    print("Next steps:")
    print("  1. Run: python tools/verify_sample_data_integrity.py")
    print("  2. Run: python tools/run_ground_truth_tests.py")

if __name__ == "__main__":
    extract_samples()

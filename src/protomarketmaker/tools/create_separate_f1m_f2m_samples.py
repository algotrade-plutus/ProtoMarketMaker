"""
Create separate F1M and F2M sample files for testing dual-file publishing

Extracts data from the rollover period (Feb 14-18, 2022) from the full
F1M and F2M files into smaller test samples.
"""
import pandas as pd
from pathlib import Path

def create_rollover_samples():
    """Create F1M and F2M sample files for rollover period"""

    # Define date range for rollover period
    start_date = '2022-02-14'
    end_date = '2022-02-18'

    # Input paths
    f1m_input = Path('data/is/VN30F1M_data.csv')
    f2m_input = Path('data/is/VN30F2M_data.csv')

    # Output paths
    output_dir = Path('data/sample')
    output_dir.mkdir(parents=True, exist_ok=True)

    f1m_output = output_dir / 'VN30F1M_rollover.csv'
    f2m_output = output_dir / 'VN30F2M_rollover.csv'

    print(f"Loading F1M data from {f1m_input}...")
    f1m_df = pd.read_csv(f1m_input, parse_dates=['datetime', 'date'])

    print(f"Loading F2M data from {f2m_input}...")
    f2m_df = pd.read_csv(f2m_input, parse_dates=['datetime', 'date'])

    # Filter by date range
    print(f"\nFiltering data for {start_date} to {end_date}...")
    f1m_filtered = f1m_df[
        (f1m_df['date'] >= start_date) &
        (f1m_df['date'] <= end_date)
    ]
    f2m_filtered = f2m_df[
        (f2m_df['date'] >= start_date) &
        (f2m_df['date'] <= end_date)
    ]

    # Save samples
    print(f"\nSaving F1M sample ({len(f1m_filtered)} rows) to {f1m_output}...")
    f1m_filtered.to_csv(f1m_output, index=False)

    print(f"Saving F2M sample ({len(f2m_filtered)} rows) to {f2m_output}...")
    f2m_filtered.to_csv(f2m_output, index=False)

    # Print summary
    print("\n" + "=" * 60)
    print("SAMPLE FILES CREATED")
    print("=" * 60)
    print(f"F1M sample: {f1m_output}")
    print(f"  Rows: {len(f1m_filtered)}")
    print(f"  Date range: {f1m_filtered['date'].min()} to {f1m_filtered['date'].max()}")
    print(f"  Contracts: {f1m_filtered['tickersymbol'].unique().tolist()}")

    print(f"\nF2M sample: {f2m_output}")
    print(f"  Rows: {len(f2m_filtered)}")
    print(f"  Date range: {f2m_filtered['date'].min()} to {f2m_filtered['date'].max()}")
    print(f"  Contracts: {f2m_filtered['tickersymbol'].unique().tolist()}")
    print("=" * 60)


if __name__ == '__main__':
    create_rollover_samples()

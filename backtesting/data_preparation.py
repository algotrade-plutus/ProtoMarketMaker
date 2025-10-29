"""
Data Preparation Script

Prepares historical data for event-driven backtest by merging
F1M and F2M data files (same format as original backtesting.py).
"""
import pandas as pd
from decimal import Decimal
from pathlib import Path
import logging


def prepare_merged_data(
    f1m_path: str,
    f2m_path: str,
    output_path: str
) -> pd.DataFrame:
    """
    Merge F1M and F2M data files into single CSV

    This replicates the data processing from original backtesting.py
    but outputs to a single merged CSV file.

    Args:
        f1m_path: Path to VN30F1M_data.csv
        f2m_path: Path to VN30F2M_data.csv
        output_path: Path for output merged CSV

    Returns:
        Merged DataFrame
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Loading F1M data from {f1m_path}")

    # Load F1M data
    f1_data = pd.read_csv(f1m_path)
    f1_data["datetime"] = pd.to_datetime(
        f1_data["datetime"], format="%Y-%m-%d %H:%M:%S.%f"
    )
    f1_data["date"] = (
        pd.to_datetime(f1_data["date"], format="%Y-%m-%d").copy().dt.date
    )

    logger.info(f"Loaded {len(f1_data)} F1M rows")
    logger.info(f"Loading F2M data from {f2m_path}")

    # Load F2M data
    f2_data = pd.read_csv(f2m_path)
    f2_data = f2_data[["date", "datetime", "tickersymbol", "price", "close"]].copy()
    f2_data["datetime"] = pd.to_datetime(
        f2_data["datetime"], format="%Y-%m-%d %H:%M:%S.%f"
    )
    f2_data["date"] = (
        pd.to_datetime(f2_data["date"], format="%Y-%m-%d").copy().dt.date
    )
    f2_data.rename(columns={"price": "f2_price", "close": "f2_close"}, inplace=True)

    logger.info(f"Loaded {len(f2_data)} F2M rows")
    logger.info("Merging data...")

    # Merge F1 and F2
    merged_data = pd.merge(
        f1_data,
        f2_data,
        on=["datetime", "date", "tickersymbol"],
        how="left"
    )

    # Forward fill missing F2 values
    merged_data = merged_data.ffill()

    logger.info(f"Merged data: {len(merged_data)} rows")

    # Save to CSV
    logger.info(f"Saving merged data to {output_path}")
    merged_data.to_csv(output_path, index=False)

    return merged_data


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Prepare historical data for event-driven backtest'
    )

    parser.add_argument('--f1m', required=True, help='Path to VN30F1M_data.csv')
    parser.add_argument('--f2m', required=True, help='Path to VN30F2M_data.csv')
    parser.add_argument('--output', required=True, help='Output path for merged CSV')
    parser.add_argument('--log-level', default='INFO', help='Logging level')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Prepare data
    prepare_merged_data(args.f1m, args.f2m, args.output)

    print(f"\n✅ Data preparation complete!")
    print(f"   Output: {args.output}")


if __name__ == '__main__':
    main()

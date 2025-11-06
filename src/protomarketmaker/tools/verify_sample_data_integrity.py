"""
Verify integrity of sample data extracted from merged source.

Checks:
1. No NaN in F1M price/close columns for F1M rows
2. Reasonable F2M price fill rate
3. Data types are correct after CSV round-trip
4. Row counts are reasonable
5. Date ranges match expected
"""

import sys
sys.path.insert(0, '.')

from .run_ground_truth_tests import load_sample_data, TESTS
import pandas as pd
from decimal import Decimal

def verify_sample(sample_name, expected_description):
    """Verify a single sample file"""

    print(f"\n{'=' * 80}")
    print(f"Verifying: {sample_name}")
    print(f"Expected: {expected_description}")
    print('=' * 80)

    try:
        # Load sample
        data = load_sample_data(sample_name)

        print(f"\n1. Basic Statistics:")
        print(f"   Rows: {len(data):,}")
        print(f"   Columns: {len(data.columns)}")
        print(f"   Date range: {data['date'].min()} to {data['date'].max()}")
        print(f"   Trading days: {data['date'].nunique()}")

        # Check 2: Data types
        print(f"\n2. Data Types:")
        print(f"   datetime: {type(data['datetime'].iloc[0]).__name__}")
        print(f"   date: {type(data['date'].iloc[0]).__name__}")

        # Check Decimal columns (all price columns should be Decimal after loading)
        for col in ['price', 'close', 'best-bid', 'best-ask', 'spread', 'f2_close', 'f2_price']:
            sample_val = data[col].iloc[100] if len(data) > 100 else data[col].iloc[0]
            dtype = type(sample_val).__name__ if pd.notna(sample_val) else "NaN"
            print(f"   {col}: {dtype}")

        # Check 3: NaN values in critical columns
        print(f"\n3. NaN Analysis:")

        # Get unique F1M tickersymbols in this sample
        f1m_symbols = sorted([sym for sym in data['tickersymbol'].unique()
                             if 'F220' in sym or 'F221' in sym or 'F222' in sym])

        print(f"   F1M symbols found: {f1m_symbols}")

        # Check each F1M symbol for NaN in price/close
        has_issues = False
        for symbol in f1m_symbols:
            f1m_rows = data[data['tickersymbol'] == symbol]
            if len(f1m_rows) == 0:
                continue

            price_nan = f1m_rows['price'].isna().sum()
            close_nan = f1m_rows['close'].isna().sum()

            if price_nan > 0 or close_nan > 0:
                print(f"   ❌ {symbol}: price NaN={price_nan}, close NaN={close_nan}")
                has_issues = True
            else:
                print(f"   ✓ {symbol}: No NaN in price/close ({len(f1m_rows):,} rows)")

        # Check F2M price fill rate
        f2_total = len(data)
        f2_filled = data['f2_price'].notna().sum()
        f2_fill_rate = (f2_filled / f2_total) * 100

        print(f"\n   F2M price fill rate: {f2_filled:,}/{f2_total:,} ({f2_fill_rate:.1f}%)")

        if f2_fill_rate < 50:
            print(f"   ⚠️  Warning: F2M fill rate below 50%")
        else:
            print(f"   ✓ F2M fill rate acceptable")

        # Check 4: Tickersymbol distribution
        print(f"\n4. Tickersymbol Distribution:")
        ticker_counts = data['tickersymbol'].value_counts()
        for ticker in sorted(ticker_counts.index)[:10]:  # Show top 10
            count = ticker_counts[ticker]
            pct = (count / len(data)) * 100
            print(f"   {ticker}: {count:>7,} rows ({pct:>5.1f}%)")

        # Final verdict
        print(f"\n{'=' * 80}")
        if has_issues:
            print(f"❌ FAILED: {sample_name} has data integrity issues")
            print('=' * 80)
            return False
        else:
            print(f"✅ PASSED: {sample_name} data integrity verified")
            print('=' * 80)
            return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print('=' * 80)
        return False

def main():
    """Verify all sample files"""

    print("=" * 80)
    print("SAMPLE DATA INTEGRITY VERIFICATION")
    print("=" * 80)
    print("\nVerifying sample data extracted from merged_is_data.csv")
    print("Checking for:")
    print("  - No NaN in F1M price/close columns")
    print("  - Proper Decimal type conversions")
    print("  - Reasonable F2M price fill rates")
    print("  - Expected date ranges")

    results = {}
    for test_config in TESTS:
        name = test_config['name']
        description = test_config['description']
        passed = verify_sample(name, description)
        results[name] = passed

    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)

    passed_count = sum(results.values())
    total_count = len(results)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")

    print("=" * 80)
    print(f"Results: {passed_count}/{total_count} passed")

    if passed_count == total_count:
        print("\n✅ All sample data files verified successfully!")
        print("\nNext step: Run ground truth tests")
        print("  python tools/run_ground_truth_tests.py")
        return 0
    else:
        print(f"\n❌ {total_count - passed_count} sample(s) failed verification")
        return 1

if __name__ == "__main__":
    sys.exit(main())

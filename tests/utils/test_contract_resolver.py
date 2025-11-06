"""
Tests for ContractSymbolResolver

This is a critical production safety component. Comprehensive testing ensures
correct contract symbol resolution to prevent trading bugs.
"""

import pytest
from datetime import date
from utils.contract_resolver import ContractSymbolResolver


class TestContractSymbolResolverAutoDetection:
    """Test auto-detection mode"""

    def test_initialization_default(self):
        """Test initialization with default parameters"""
        resolver = ContractSymbolResolver()
        assert resolver.reference_date == date.today()
        assert resolver.manual_mappings is None
        assert resolver._expiration_cache == {}

    def test_initialization_with_reference_date(self):
        """Test initialization with custom reference date"""
        ref_date = date(2025, 10, 15)
        resolver = ContractSymbolResolver(reference_date=ref_date)
        assert resolver.reference_date == ref_date

    def test_resolve_f1m_before_expiration(self):
        """Test F1M resolution before expiration"""
        # Oct 15, 2025 (before Oct 16 expiration)
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        result = resolver.resolve('VN30F1M')
        assert result == 'VN30F2510'  # October 2025

    def test_resolve_f2m_before_expiration(self):
        """Test F2M resolution before expiration"""
        # Oct 15, 2025 (before Oct 16 expiration)
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        result = resolver.resolve('VN30F2M')
        assert result == 'VN30F2511'  # November 2025

    def test_resolve_on_expiration_day(self):
        """Test resolution on expiration day (third Thursday)"""
        # Oct 16, 2025 is third Thursday - still trades 2510
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 16))
        result = resolver.resolve('VN30F1M')
        assert result == 'VN30F2510'

    def test_resolve_after_expiration(self):
        """Test resolution after expiration (rolls to next month)"""
        # Oct 17, 2025 (after Oct 16 expiration)
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 17))
        result_f1 = resolver.resolve('VN30F1M')
        result_f2 = resolver.resolve('VN30F2M')
        assert result_f1 == 'VN30F2511'  # November 2025
        assert result_f2 == 'VN30F2512'  # December 2025

    def test_resolve_actual_contract_code(self):
        """Test that actual contract codes pass through unchanged"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        result = resolver.resolve('VN30F2510')
        assert result == 'VN30F2510'  # No change

    def test_resolve_all(self):
        """Test resolving multiple symbols"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        symbols = ['VN30F1M', 'VN30F2M']
        results = resolver.resolve_all(symbols)
        assert results == ['VN30F2510', 'VN30F2511']

    def test_resolve_mixed_symbols(self):
        """Test resolving mix of informal and actual codes"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        symbols = ['VN30F1M', 'VN30F2601', 'VN30F2M']
        results = resolver.resolve_all(symbols)
        assert results == ['VN30F2510', 'VN30F2601', 'VN30F2511']

    def test_year_rollover(self):
        """Test resolution across year boundary"""
        # Dec 31, 2025
        resolver = ContractSymbolResolver(reference_date=date(2025, 12, 31))
        result_f1 = resolver.resolve('VN30F1M')
        result_f2 = resolver.resolve('VN30F2M')
        assert result_f1 == 'VN30F2601'  # January 2026
        assert result_f2 == 'VN30F2602'  # February 2026


class TestContractSymbolResolverManualMode:
    """Test manual override mode"""

    def test_manual_mappings(self):
        """Test manual symbol mappings"""
        mappings = {
            'VN30F1M': 'VN30F2510',
            'VN30F2M': 'VN30F2511'
        }
        resolver = ContractSymbolResolver(manual_mappings=mappings)

        assert resolver.resolve('VN30F1M') == 'VN30F2510'
        assert resolver.resolve('VN30F2M') == 'VN30F2511'

    def test_manual_mappings_unmapped_symbol(self):
        """Test that unmapped symbols pass through in manual mode"""
        mappings = {'VN30F1M': 'VN30F2510'}
        resolver = ContractSymbolResolver(manual_mappings=mappings)

        # Unmapped symbol passes through
        assert resolver.resolve('VN30F2512') == 'VN30F2512'

    def test_manual_mappings_ignores_auto_detection(self):
        """Test that manual mappings disable auto-detection"""
        # Reference date would auto-detect to 2510, but manual overrides
        mappings = {'VN30F1M': 'VN30F2601'}
        resolver = ContractSymbolResolver(
            reference_date=date(2025, 10, 15),
            manual_mappings=mappings
        )

        assert resolver.resolve('VN30F1M') == 'VN30F2601'


class TestExpirationDateCalculation:
    """Test expiration date calculation"""

    def test_get_expiration_date_october_2025(self):
        """Test expiration calculation for October 2025"""
        resolver = ContractSymbolResolver()
        expiration = resolver.get_expiration_date('VN30F2510')
        assert expiration == date(2025, 10, 16)  # Third Thursday

    def test_get_expiration_date_november_2025(self):
        """Test expiration calculation for November 2025"""
        resolver = ContractSymbolResolver()
        expiration = resolver.get_expiration_date('VN30F2511')
        assert expiration == date(2025, 11, 20)  # Third Thursday

    def test_get_expiration_date_january_2026(self):
        """Test expiration calculation for January 2026"""
        resolver = ContractSymbolResolver()
        expiration = resolver.get_expiration_date('VN30F2601')
        assert expiration == date(2026, 1, 15)  # Third Thursday

    def test_get_expiration_date_invalid_format(self):
        """Test error handling for invalid contract code"""
        resolver = ContractSymbolResolver()

        with pytest.raises(ValueError, match="Invalid contract code format"):
            resolver.get_expiration_date('INVALID')

        with pytest.raises(ValueError, match="Invalid contract code format"):
            resolver.get_expiration_date('VN30F25')

    def test_get_expiration_date_invalid_month(self):
        """Test error handling for invalid month"""
        resolver = ContractSymbolResolver()

        with pytest.raises(ValueError, match="Invalid month"):
            resolver.get_expiration_date('VN30F2513')  # Month 13

    def test_get_expiration_date_caching(self):
        """Test that expiration dates are cached"""
        resolver = ContractSymbolResolver()

        # First call
        exp1 = resolver.get_expiration_date('VN30F2510')
        cache_size_1 = len(resolver._expiration_cache)

        # Second call (should use cache)
        exp2 = resolver.get_expiration_date('VN30F2510')
        cache_size_2 = len(resolver._expiration_cache)

        assert exp1 == exp2
        assert cache_size_1 == cache_size_2  # Cache not grown


class TestDaysToExpiration:
    """Test days to expiration calculation"""

    def test_days_to_expiration_one_day_before(self):
        """Test one day before expiration"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        days = resolver.get_days_to_expiration('VN30F2510')
        assert days == 1

    def test_days_to_expiration_on_day(self):
        """Test on expiration day"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 16))
        days = resolver.get_days_to_expiration('VN30F2510')
        assert days == 0

    def test_days_to_expiration_after(self):
        """Test after expiration"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 17))
        days = resolver.get_days_to_expiration('VN30F2510')
        assert days == -1

    def test_is_expiration_day_true(self):
        """Test expiration day check returns True"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 16))
        assert resolver.is_expiration_day('VN30F2510') is True

    def test_is_expiration_day_false(self):
        """Test expiration day check returns False"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        assert resolver.is_expiration_day('VN30F2510') is False


class TestResolutionSummary:
    """Test resolution summary generation"""

    def test_get_resolution_summary(self):
        """Test resolution summary for display"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        symbols = ['VN30F1M', 'VN30F2M']

        summary = resolver.get_resolution_summary(symbols)

        assert 'VN30F1M' in summary
        assert 'VN30F2M' in summary

        # Check F1M
        f1_info = summary['VN30F1M']
        assert f1_info['code'] == 'VN30F2510'
        assert f1_info['expiration'] == date(2025, 10, 16)
        assert f1_info['days_to_expiry'] == 1

        # Check F2M
        f2_info = summary['VN30F2M']
        assert f2_info['code'] == 'VN30F2511'
        assert f2_info['expiration'] == date(2025, 11, 20)
        assert f2_info['days_to_expiry'] == 36

    def test_get_resolution_summary_with_actual_codes(self):
        """Test resolution summary with actual contract codes"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 10, 15))
        symbols = ['VN30F2512']

        summary = resolver.get_resolution_summary(symbols)

        assert 'VN30F2512' in summary
        info = summary['VN30F2512']
        assert info['code'] == 'VN30F2512'
        assert info['expiration'] == date(2025, 12, 18)


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_february_leap_year(self):
        """Test February in leap year"""
        resolver = ContractSymbolResolver(reference_date=date(2024, 2, 1))
        expiration = resolver.get_expiration_date('VN30F2402')
        # Third Thursday of February 2024
        assert expiration.year == 2024
        assert expiration.month == 2
        assert expiration.weekday() == 3  # Thursday

    def test_february_non_leap_year(self):
        """Test February in non-leap year"""
        resolver = ContractSymbolResolver(reference_date=date(2025, 2, 1))
        expiration = resolver.get_expiration_date('VN30F2502')
        assert expiration.year == 2025
        assert expiration.month == 2
        assert expiration.weekday() == 3  # Thursday

    def test_december_to_january_rollover(self):
        """Test rollover from December to January"""
        # After December expiration
        resolver = ContractSymbolResolver(reference_date=date(2025, 12, 19))
        f1 = resolver.resolve('VN30F1M')
        f2 = resolver.resolve('VN30F2M')

        assert f1 == 'VN30F2601'  # January 2026
        assert f2 == 'VN30F2602'  # February 2026


class TestContractSymbolResolverFromCSV:
    """Test auto-detection from CSV data"""

    def test_from_csv_basic(self):
        """Test basic from_csv() functionality"""
        resolver = ContractSymbolResolver.from_csv('data/sample/merged_is_data_1day.csv')

        # Should detect VN30F2202 and VN30F2203 from February 2022 data
        assert resolver.resolve('VN30F1M') == 'VN30F2202'
        assert resolver.resolve('VN30F2M') == 'VN30F2203'

    def test_from_csv_with_reference_date(self):
        """Test from_csv() with explicit reference date"""
        # Use a date early in February 2022
        resolver = ContractSymbolResolver.from_csv(
            'data/sample/merged_is_data_1day.csv',
            reference_date=date(2022, 2, 7)
        )

        assert resolver.resolve('VN30F1M') == 'VN30F2202'
        assert resolver.resolve('VN30F2M') == 'VN30F2203'

    def test_from_csv_resolver_has_manual_mappings(self):
        """Test that from_csv() creates manual mappings"""
        resolver = ContractSymbolResolver.from_csv('data/sample/merged_is_data_1day.csv')

        assert resolver.manual_mappings is not None
        assert 'VN30F1M' in resolver.manual_mappings
        assert 'VN30F2M' in resolver.manual_mappings

    def test_from_csv_expiration_dates(self):
        """Test that detected contracts have correct expiration dates"""
        resolver = ContractSymbolResolver.from_csv('data/sample/merged_is_data_1day.csv')

        f1_code = resolver.resolve('VN30F1M')
        f2_code = resolver.resolve('VN30F2M')

        # Get expiration dates
        f1_exp = resolver.get_expiration_date(f1_code)
        f2_exp = resolver.get_expiration_date(f2_code)

        # F2 should expire after F1
        assert f2_exp > f1_exp

        # Both should be Thursdays
        assert f1_exp.weekday() == 3
        assert f2_exp.weekday() == 3

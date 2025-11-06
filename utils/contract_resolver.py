"""
Contract Symbol Resolver for Vietnamese VN30 Futures

This module provides utilities to resolve informal contract symbols (VN30F1M, VN30F2M)
to actual exchange contract codes (VN30F2510, VN30F2511, etc.).

Vietnamese VN30 futures contracts:
- Expire on third Thursday of each month
- Named with format: VN30F[YY][MM] (e.g., VN30F2510 = October 2025)
- F1M = front month, F2M = second month

Example:
    # Auto-detection mode
    resolver = ContractSymbolResolver()
    f1_code = resolver.resolve('VN30F1M')  # Returns 'VN30F2510' on Oct 15, 2025
    f2_code = resolver.resolve('VN30F2M')  # Returns 'VN30F2511' on Oct 15, 2025

    # Manual override mode
    resolver = ContractSymbolResolver(manual_mappings={
        'VN30F1M': 'VN30F2510',
        'VN30F2M': 'VN30F2511'
    })
    f1_code = resolver.resolve('VN30F1M')  # Returns 'VN30F2510' (from config)
"""

from datetime import date
from dateutil.rrule import rrule, MONTHLY, TH
from typing import Dict, Optional, Tuple, List
import pandas as pd
import re


class ContractSymbolResolver:
    """
    Resolves informal contract symbols (VN30F1M, VN30F2M) to actual
    exchange contract codes (VN30F2510, VN30F2511, etc.)

    This is a critical production safety feature. Wrong ticker symbols have
    caused many bugs in live trading systems.
    """

    def __init__(
        self,
        reference_date: Optional[date] = None,
        manual_mappings: Optional[Dict[str, str]] = None,
        auto_detect: bool = True
    ):
        """
        Initialize contract symbol resolver

        Args:
            reference_date: Date to use for auto-detection (default: today)
            manual_mappings: Manual symbol mappings (disables auto-detection)
                Example: {'VN30F1M': 'VN30F2510', 'VN30F2M': 'VN30F2511'}
            auto_detect: Enable auto-detection based on reference_date (default: True)
        """
        self.reference_date = reference_date or date.today()
        self.manual_mappings = manual_mappings
        self.auto_detect = auto_detect if manual_mappings is None else False
        self._expiration_cache: Dict[Tuple[int, int], date] = {}

    @classmethod
    def from_csv(cls, csv_path: str, reference_date: Optional[date] = None) -> 'ContractSymbolResolver':
        """
        Create resolver by detecting contracts from CSV data

        Automatically detects F1M and F2M contracts by:
        1. Reading tickersymbol column from CSV
        2. Finding VN30F contracts
        3. Determining which is front month (F1M) and second month (F2M)

        Args:
            csv_path: Path to CSV file with 'tickersymbol' column
            reference_date: Date to use as reference (default: first date in CSV)

        Returns:
            ContractSymbolResolver with detected mappings

        Example:
            resolver = ContractSymbolResolver.from_csv('data/sample/merged_is_data_1day.csv')
            f1_code = resolver.resolve('VN30F1M')  # Returns detected F1 code
        """
        import pandas as pd

        # Read CSV
        df = pd.read_csv(csv_path)

        if 'tickersymbol' not in df.columns:
            raise ValueError(f"CSV must have 'tickersymbol' column. Found: {df.columns.tolist()}")

        # Get unique VN30F contracts
        contracts = df['tickersymbol'].unique()
        vn30_contracts = [c for c in contracts if isinstance(c, str) and c.startswith('VN30F')]

        if len(vn30_contracts) == 0:
            raise ValueError("No VN30F contracts found in CSV")

        # Parse contract codes to get year/month
        contract_dates = []
        for contract in vn30_contracts:
            match = re.match(r'VN30F(\d{2})(\d{2})', contract)
            if match:
                yy, mm = match.groups()
                year = 2000 + int(yy)
                month = int(mm)
                contract_dates.append((contract, year, month))

        if len(contract_dates) == 0:
            raise ValueError(f"Could not parse any contract codes from: {vn30_contracts}")

        # Sort by expiration date
        contract_dates.sort(key=lambda x: (x[1], x[2]))

        # Determine reference date
        if reference_date is None:
            if 'datetime' in df.columns:
                reference_date = pd.to_datetime(df['datetime'].iloc[0]).date()
            else:
                reference_date = date.today()

        # Find F1M (soonest to expire after reference_date) and F2M (next one)
        f1_contract = None
        f2_contract = None

        temp_resolver = cls(reference_date=reference_date, auto_detect=False)

        for contract, year, month in contract_dates:
            exp_date = temp_resolver._calculate_expiration_date(year, month)
            if exp_date >= reference_date:
                if f1_contract is None:
                    f1_contract = contract
                elif f2_contract is None:
                    f2_contract = contract
                    break

        # Create mappings
        mappings = {}
        if f1_contract:
            mappings['VN30F1M'] = f1_contract
        if f2_contract:
            mappings['VN30F2M'] = f2_contract

        if not mappings:
            raise ValueError(f"Could not determine F1M/F2M from contracts: {vn30_contracts}")

        return cls(reference_date=reference_date, manual_mappings=mappings, auto_detect=False)

    def resolve(self, informal_symbol: str) -> str:
        """
        Resolve informal symbol to actual contract code

        Args:
            informal_symbol: Informal symbol like 'VN30F1M' or 'VN30F2M'

        Returns:
            Actual contract code like 'VN30F2510'

        Raises:
            ValueError: If symbol format is invalid
        """
        # If manual mappings provided, use them
        if self.manual_mappings:
            if informal_symbol in self.manual_mappings:
                return self.manual_mappings[informal_symbol]
            else:
                # Not an informal symbol, return as-is (might be actual code)
                return informal_symbol

        # Auto-detection mode
        if informal_symbol == 'VN30F1M':
            return self._get_front_month_code()
        elif informal_symbol == 'VN30F2M':
            return self._get_second_month_code()
        else:
            # Not an informal symbol, assume it's already an actual code
            return informal_symbol

    def resolve_all(self, symbols: List[str]) -> List[str]:
        """
        Resolve list of symbols

        Args:
            symbols: List of informal symbols

        Returns:
            List of resolved contract codes
        """
        return [self.resolve(symbol) for symbol in symbols]

    def get_expiration_date(self, contract_code: str) -> date:
        """
        Get expiration date for a contract code

        Args:
            contract_code: Contract code like 'VN30F2510'

        Returns:
            Expiration date (third Thursday of month)

        Raises:
            ValueError: If contract code format is invalid

        Example:
            >>> resolver.get_expiration_date('VN30F2510')
            datetime.date(2025, 10, 16)
        """
        # Parse contract code: VN30F2510 → year=2025, month=10
        # Format: VN30F + YYMM (5 + 4 = 9 characters)
        if not contract_code.startswith('VN30F') or len(contract_code) != 9:
            raise ValueError(f"Invalid contract code format: {contract_code}")

        year_part = contract_code[5:7]  # "25"
        month_part = contract_code[7:9]  # "10"

        try:
            year = 2000 + int(year_part)
            month = int(month_part)
        except ValueError:
            raise ValueError(f"Invalid year/month in contract code: {contract_code}")

        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month in contract code: {contract_code}")

        return self._calculate_expiration_date(year, month)

    def get_days_to_expiration(self, contract_code: str) -> int:
        """
        Get days remaining until contract expiration

        Args:
            contract_code: Contract code like 'VN30F2510'

        Returns:
            Number of days to expiration (negative if expired)
        """
        expiration = self.get_expiration_date(contract_code)
        return (expiration - self.reference_date).days

    def is_expiration_day(self, contract_code: str) -> bool:
        """
        Check if reference date is the expiration day

        Args:
            contract_code: Contract code like 'VN30F2510'

        Returns:
            True if today is expiration day, False otherwise
        """
        return self.get_days_to_expiration(contract_code) == 0

    def get_resolution_summary(self, symbols: List[str]) -> Dict[str, dict]:
        """
        Get detailed resolution summary for display

        Args:
            symbols: List of informal symbols

        Returns:
            Dictionary mapping informal → {code, expiration, days_to_expiry}

        Example:
            >>> resolver.get_resolution_summary(['VN30F1M', 'VN30F2M'])
            {
                'VN30F1M': {
                    'code': 'VN30F2510',
                    'expiration': datetime.date(2025, 10, 16),
                    'days_to_expiry': 1
                },
                'VN30F2M': {
                    'code': 'VN30F2511',
                    'expiration': datetime.date(2025, 11, 20),
                    'days_to_expiry': 36
                }
            }
        """
        summary = {}
        for symbol in symbols:
            code = self.resolve(symbol)
            expiration = self.get_expiration_date(code)
            days = self.get_days_to_expiration(code)

            summary[symbol] = {
                'code': code,
                'expiration': expiration,
                'days_to_expiry': days
            }

        return summary

    def _get_front_month_code(self) -> str:
        """Get F1 (front month) contract code"""
        expirations = self._get_next_n_expirations(2)
        year, month = expirations[0]
        return f"VN30F{year % 100:02d}{month:02d}"

    def _get_second_month_code(self) -> str:
        """Get F2 (second month) contract code"""
        expirations = self._get_next_n_expirations(2)
        year, month = expirations[1]
        return f"VN30F{year % 100:02d}{month:02d}"

    def _get_next_n_expirations(self, n: int) -> List[Tuple[int, int]]:
        """
        Get next N expiration months from reference date

        Args:
            n: Number of expiration months to return

        Returns:
            List of (year, month) tuples
        """
        result = []
        current_year = self.reference_date.year
        current_month = self.reference_date.month

        # Generate next 12 months
        for i in range(12):
            year = current_year + (current_month + i - 1) // 12
            month = (current_month + i - 1) % 12 + 1

            expiration = self._calculate_expiration_date(year, month)

            # Include if expiration is today or in the future
            if expiration >= self.reference_date:
                result.append((year, month))

            if len(result) >= n:
                break

        return result

    def _calculate_expiration_date(self, year: int, month: int) -> date:
        """
        Calculate third Thursday of given month

        Vietnamese VN30 futures expire on the third Thursday of each month.

        Args:
            year: Year (e.g., 2025)
            month: Month (1-12)

        Returns:
            Date of third Thursday
        """
        # Check cache
        key = (year, month)
        if key in self._expiration_cache:
            return self._expiration_cache[key]

        # Use dateutil.rrule to find third Thursday
        # Start from first day of month
        start_date = date(year, month, 1)

        # Find all Thursdays in the month
        thursdays = list(rrule(
            MONTHLY,
            byweekday=TH,
            dtstart=start_date,
            count=3
        ))

        # Third Thursday
        expiration = thursdays[2].date()

        # Cache result
        self._expiration_cache[key] = expiration

        return expiration

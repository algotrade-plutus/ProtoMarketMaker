"""Smoke + unit tests for proto_market_maker."""
from decimal import Decimal

import pandas as pd

import proto_market_maker
from proto_market_maker.utils import round_decimal


def test_package_imports_and_has_version():
    assert isinstance(proto_market_maker.__version__, str)


def test_entry_modules_import():
    import proto_market_maker.backtest  # noqa: F401
    import proto_market_maker.evaluate  # noqa: F401
    import proto_market_maker.optimize  # noqa: F401
    import proto_market_maker.data_loader  # noqa: F401


def test_round_decimal_returns_decimal():
    # round_decimal(df, column, digits=10) rounds a DataFrame column to `digits`
    # decimal places and converts each value to Decimal.
    # Assert: 1.23456789012345 rounded to 10 digits gives Decimal("1.2345678901").
    df = pd.DataFrame({"val": [1.23456789012345]})
    result = round_decimal(df, "val", digits=10)
    assert isinstance(result["val"][0], Decimal)
    assert result["val"][0] == Decimal("1.2345678901")

"""
Pytest configuration for ProtoMarketMaker tests.

This conftest.py ensures that the src/protomarketmaker package is importable
when running tests, enabling the use of absolute package imports.
"""
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Also add the project root for backward compatibility during migration
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Common fixtures can be added here
import pytest
from decimal import Decimal
from datetime import datetime


@pytest.fixture
def sample_decimal():
    """Provide a sample Decimal for tests."""
    return Decimal("1250.50")


@pytest.fixture
def sample_datetime():
    """Provide a sample datetime for tests."""
    return datetime(2025, 1, 15, 10, 30, 0)


@pytest.fixture
def sample_contract_config():
    """Provide sample contract configuration."""
    return {
        "f1m_symbol": "VN30F1M",
        "f2m_symbol": "VN30F2M",
        "contract_multiplier": 100,
        "margin_requirement": 0.17,
    }

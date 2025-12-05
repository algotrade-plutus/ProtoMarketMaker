"""
Unit tests for Trading Session
"""
import pytest
from decimal import Decimal
import pandas as pd
from datetime import datetime

from protomarketmaker.paper_trading.session import TradingSession


class TestTradingSession:
    """Test trading session functionality"""

    def test_initialization(self):
        """Test session initialization"""
        session = TradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        assert session.initial_capital == Decimal("500000")
        assert session.step == Decimal("2.9")
        assert session.portfolio is not None
        assert session.oms is not None
        assert session.strategy is not None
        assert session.execution is not None

    def test_run_backtest_with_sample_data(self):
        """Test running backtest with sample data"""
        session = TradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        # Create sample data
        data = pd.DataFrame({
            'datetime': [datetime(2025, 1, 1, 10, 0, 0)] * 5,
            'tickersymbol': ['VN30F1M'] * 5,
            'price': [1250, 1251, 1250, 1249, 1250],
            'best-bid': [1249, 1250, 1249, 1248, 1249],
            'best-ask': [1251, 1252, 1251, 1250, 1251],
            'spread': [2, 2, 2, 2, 2]
        })

        summary = session.run_backtest(data)

        # Verify summary structure
        assert 'portfolio' in summary
        assert 'orders' in summary
        assert 'performance' in summary

        assert 'initial_capital' in summary['portfolio']
        assert 'final_nav' in summary['portfolio']
        assert 'total_return' in summary['portfolio']

    def test_get_summary(self):
        """Test getting session summary"""
        session = TradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        summary = session.get_summary()

        assert summary['portfolio']['initial_capital'] == 500000
        assert 'final_nav' in summary['portfolio']
        assert 'total_return' in summary['portfolio']
        assert 'orders' in summary

    def test_reset(self):
        """Test session reset"""
        session = TradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        # Run some data
        data = pd.DataFrame({
            'datetime': [datetime(2025, 1, 1, 10, 0, 0)],
            'tickersymbol': ['VN30F1M'],
            'price': [1250],
            'best-bid': [1249],
            'best-ask': [1251],
            'spread': [2]
        })
        session.run_backtest(data)

        # Reset
        session.reset()

        # Verify reset
        assert session.portfolio.cash == Decimal("500000")
        summary = session.get_summary()
        assert summary['orders']['total_orders'] == 0

    def test_backtest_with_fills(self):
        """Test backtest that generates fills"""
        session = TradingSession(
            initial_capital=Decimal("500000"),
            step=Decimal("2.9")
        )

        # Create data that will fill orders
        data = pd.DataFrame({
            'datetime': [
                datetime(2025, 1, 1, 10, 0, 0),
                datetime(2025, 1, 1, 10, 0, 15),
                datetime(2025, 1, 1, 10, 0, 30),
            ],
            'tickersymbol': ['VN30F1M', 'VN30F1M', 'VN30F1M'],
            'price': [1250, 1247, 1253],  # Moves to hit bid then ask
            'best-bid': [1249, 1246, 1252],
            'best-ask': [1251, 1248, 1254],
            'spread': [2, 2, 2]
        })

        summary = session.run_backtest(data)

        # Should have some filled orders
        assert summary['orders']['filled_orders'] > 0

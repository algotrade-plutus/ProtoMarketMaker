"""
Event-Driven Backtesting Module

Provides backtesting capabilities using the event-driven architecture.
"""
from backtesting.data_feed import HistoricalDataFeed
from backtesting.engine import BacktestingEngine
from backtesting.results import BacktestResults

__all__ = [
    'HistoricalDataFeed',
    'BacktestingEngine',
    'BacktestResults',
]

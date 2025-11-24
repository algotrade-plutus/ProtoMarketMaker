"""
Event-driven backtesting system

Provides comprehensive backtesting capabilities:
- Data feed for historical data replay
- Event-driven backtest engine
- Result comparison utilities
- Data preparation tools
"""

from .data_feed import HistoricalDataFeed
from .engine import BacktestingEngine
from .results import BacktestResults
from .comparison import BacktestComparison

__all__ = [
    'HistoricalDataFeed',
    'BacktestingEngine',
    'BacktestResults',
    'BacktestComparison',
]

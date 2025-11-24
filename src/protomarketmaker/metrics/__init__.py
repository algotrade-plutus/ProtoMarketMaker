"""
Performance metrics and calculations

Provides performance metric calculations:
- Sharpe ratio
- Sortino ratio
- Maximum drawdown
- HPR (Holding Period Return)
- Information ratio
"""

from .metric import Metric

__all__ = [
    'Metric',
]

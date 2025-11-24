"""
Real-time monitoring and evaluation

Provides monitoring capabilities:
- Performance monitor
- Terminal dashboard
"""

from .monitor import PerformanceMonitor
from .dashboard import TradingDashboard

__all__ = [
    'PerformanceMonitor',
    'TradingDashboard',
]
"""
Configuration management

Provides configuration loading capabilities:
- JSON config file loader
- Environment variable management
- Database parameters
- Redis configuration
"""

from .config import (
    BACKTESTING_CONFIG,
    OPTIMIZATION_CONFIG,
    BEST_CONFIG,
    REDIS_CONFIG,
    db_params,
)

__all__ = [
    'BACKTESTING_CONFIG',
    'OPTIMIZATION_CONFIG',
    'BEST_CONFIG',
    'REDIS_CONFIG',
    'db_params',
]

"""
Redis-based paper trading system

Provides production-ready paper trading capabilities:
- Redis paper trading engine
- CLI runner with contract resolution
- Results export (JSON)
- Audit logging
- Event recording
"""

from .engine import RedisPaperTradingEngine
from .results import PaperTradingResults
from .audit_logger import AuditLogger

__all__ = [
    'RedisPaperTradingEngine',
    'PaperTradingResults',
    'AuditLogger',
]
"""
Connectors Module

Provides adapters for connecting to external trading systems and data sources.
Currently supports:
- PaperBroker FIX protocol for order execution
"""

from .paperbroker_connector import PaperBrokerConnector

__all__ = ['PaperBrokerConnector']
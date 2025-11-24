"""
Core event-driven architecture components

Provides the fundamental building blocks for the trading system:
- Event bus for publish-subscribe messaging
- Event types (MarketData, Signal, Order, Fill, Time, Rollover)
- Order model with lifecycle tracking
- Position model with PnL calculation
- Enumerations (EventType, OrderSide, OrderStatus)
"""

from .event import (
    EventBus,
    Event,
    MarketDataEvent,
    SignalEvent,
    OrderEvent,
    FillEvent,
    TimeEvent,
    RolloverEvent,
)
from .order import Order
from .position import Position
from .enums import EventType, OrderSide, OrderStatus

__all__ = [
    # Event system
    'EventBus',
    'Event',
    'MarketDataEvent',
    'SignalEvent',
    'OrderEvent',
    'FillEvent',
    'TimeEvent',
    'RolloverEvent',
    # Models
    'Order',
    'Position',
    # Enums
    'EventType',
    'OrderSide',
    'OrderStatus',
]

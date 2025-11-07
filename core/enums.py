"""
Enumeration types for paper trading system
"""
from enum import Enum


class EventType(Enum):
    """Types of events in the trading system"""
    MARKET_DATA = "MARKET_DATA"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    TIME = "TIME"
    SYSTEM = "SYSTEM"
    ROLLOVER = "ROLLOVER"


class OrderSide(Enum):
    """Order side (buy/sell)"""
    BID = "BID"
    ASK = "ASK"

    def __str__(self):
        return self.value


class OrderStatus(Enum):
    """Order lifecycle states"""
    CREATED = "CREATED"
    PENDING_SUBMIT = "PENDING_SUBMIT"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"  # Order acknowledged by exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

    def __str__(self):
        return self.value

    def is_active(self) -> bool:
        """Check if order is in active state"""
        return self in [
            OrderStatus.PENDING_SUBMIT,
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED
        ]

    def is_terminal(self) -> bool:
        """Check if order is in terminal state"""
        return self in [
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED
        ]

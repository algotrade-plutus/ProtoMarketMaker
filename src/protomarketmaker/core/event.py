"""
Event system for paper trading
Based on event-driven architecture pattern
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Dict, List
from queue import Queue
import logging

from .enums import EventType


@dataclass
class Event:
    """
    Base class for all events in the trading system

    All events have:
    - event_type: Classification of event
    - timestamp: When event occurred
    """
    event_type: Optional[EventType] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate timestamp is timezone-aware if needed"""
        if not isinstance(self.timestamp, datetime):
            raise TypeError(f"timestamp must be datetime, got {type(self.timestamp)}")


@dataclass
class MarketDataEvent(Event):
    """
    Market price update event

    Published when new market data arrives from Redis/Kafka
    """
    contract: str = ""  # "VN30F1M" or "VN30F2M"
    price: Decimal = Decimal('0')
    bid: Decimal = Decimal('0')
    ask: Decimal = Decimal('0')
    spread: Decimal = Decimal('0')
    volume: int = 0

    def __post_init__(self):
        if not self.event_type or self.event_type != EventType.MARKET_DATA:
            object.__setattr__(self, 'event_type', EventType.MARKET_DATA)
        super().__post_init__()


@dataclass
class SignalEvent(Event):
    """
    Strategy signal event

    Published when strategy generates new bid/ask prices
    """
    contract: str = ""
    signal_type: str = ""  # "UPDATE_BID_ASK"
    bid_price: Decimal = Decimal('0')
    ask_price: Decimal = Decimal('0')
    reason: str = ""  # "TIME_ELAPSED", "ORDER_FILLED", "INITIAL"

    def __post_init__(self):
        if not self.event_type or self.event_type != EventType.SIGNAL:
            object.__setattr__(self, 'event_type', EventType.SIGNAL)
        super().__post_init__()


@dataclass
class OrderEvent(Event):
    """
    Order lifecycle event

    Published when order state changes
    """
    order_id: str = ""
    contract: str = ""
    side: str = ""  # "BID" or "ASK"
    price: Decimal = Decimal('0')
    quantity: int = 1
    status: str = "CREATED"  # OrderStatus value

    def __post_init__(self):
        if not self.event_type or self.event_type != EventType.ORDER:
            object.__setattr__(self, 'event_type', EventType.ORDER)
        super().__post_init__()


@dataclass
class FillEvent(Event):
    """
    Order execution event

    Published when order is matched/filled
    """
    order_id: str = ""
    contract: str = ""
    side: str = ""  # "BID" or "ASK"
    fill_price: Decimal = Decimal('0')
    fill_quantity: int = 0
    fee: Decimal = Decimal('0')

    def __post_init__(self):
        if not self.event_type or self.event_type != EventType.FILL:
            object.__setattr__(self, 'event_type', EventType.FILL)
        super().__post_init__()


@dataclass
class TimeEvent(Event):
    """
    Scheduled time event

    Published by scheduler for daily settlement, expiration, etc.
    """
    event_name: str = ""  # "DAILY_SETTLEMENT", "CONTRACT_EXPIRATION"
    date: Optional[datetime] = None

    def __post_init__(self):
        if not self.event_type or self.event_type != EventType.TIME:
            object.__setattr__(self, 'event_type', EventType.TIME)
        super().__post_init__()


@dataclass
class RolloverEvent(Event):
    """
    Contract rollover event

    Published when futures contract expires and needs to roll to next month
    (e.g., VN30F2201 -> VN30F2202 on expiration)
    """
    old_contract: str = ""  # "VN30F2201"
    new_contract: str = ""  # "VN30F2202"
    old_price: Decimal = Decimal('0')  # Last price of expiring contract
    new_price: Decimal = Decimal('0')  # First price of new contract

    def __post_init__(self):
        if not self.event_type or self.event_type != EventType.ROLLOVER:
            object.__setattr__(self, 'event_type', EventType.ROLLOVER)
        super().__post_init__()


class EventBus:
    """
    Central event dispatcher using publish-subscribe pattern

    Components subscribe to event types they want to handle.
    When an event is published, all registered handlers are invoked.

    Example:
        bus = EventBus()
        bus.subscribe(EventType.MARKET_DATA, my_handler)
        bus.publish(MarketDataEvent(...))
        bus.process_events()  # Calls my_handler
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._event_queue: Queue = Queue()
        self.logger = logging.getLogger(__name__)
        self._event_count = 0

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]):
        """
        Register event handler for specific event type

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function(event) -> None
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)
        self.logger.info(
            f"Handler '{handler.__name__}' subscribed to {event_type.value}"
        )

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Remove handler from event type"""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            self.logger.info(
                f"Handler '{handler.__name__}' unsubscribed from {event_type.value}"
            )

    def publish(self, event: Event):
        """
        Publish event to queue

        Args:
            event: Event instance to publish
        """
        self._event_queue.put(event)
        self._event_count += 1

    def process_events(self):
        """
        Process all queued events

        Dispatches each event to registered handlers.
        Exceptions in handlers are caught and logged.
        """
        processed = 0
        while not self._event_queue.empty():
            event = self._event_queue.get()
            event_type = event.event_type

            if event_type in self._handlers:
                for handler in self._handlers[event_type]:
                    try:
                        handler(event)
                        processed += 1
                    except Exception as e:
                        self.logger.error(
                            f"Error in handler '{handler.__name__}' "
                            f"for {event_type.value}: {e}",
                            exc_info=True
                        )

        return processed

    def get_event_count(self) -> int:
        """Get total events published"""
        return self._event_count

    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self._event_queue.qsize()

    def clear_queue(self):
        """Clear all pending events"""
        while not self._event_queue.empty():
            self._event_queue.get()

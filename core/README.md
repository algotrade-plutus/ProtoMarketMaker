# Core Module - Event-Driven Trading Infrastructure

The `core` module provides fundamental data structures and event system for the paper trading system.

## Components

### 1. Event System ([event.py](event.py))

Event-driven architecture using publish-subscribe pattern.

#### Events

- **MarketDataEvent**: Market price updates
- **SignalEvent**: Strategy signals (bid/ask updates)
- **OrderEvent**: Order lifecycle changes
- **FillEvent**: Order executions
- **TimeEvent**: Scheduled events (daily settlement, expiration)

#### EventBus

Central event dispatcher that routes events to registered handlers.

**Example Usage**:

```python
from core.event import EventBus, MarketDataEvent
from core.enums import EventType
from decimal import Decimal

# Create event bus
bus = EventBus()

# Subscribe handler
def handle_market_data(event):
    print(f"Price update: {event.contract} @ {event.price}")

bus.subscribe(EventType.MARKET_DATA, handle_market_data)

# Publish event
event = MarketDataEvent(
    contract="VN30F1M",
    price=Decimal("1250.5"),
    bid=Decimal("1250.0"),
    ask=Decimal("1251.0"),
    spread=Decimal("1.0")
)
bus.publish(event)

# Process events
bus.process_events()
```

### 2. Order Model ([order.py](order.py))

Order data structure with lifecycle tracking.

**Example Usage**:

```python
from core.order import Order
from core.enums import OrderSide, OrderStatus
from decimal import Decimal

# Create order
order = Order(
    contract="VN30F1M",
    side=OrderSide.BID,
    price=Decimal("1250.5"),
    quantity=1
)

print(order.order_id)  # Auto-generated UUID
print(order.is_active())  # False (status is CREATED)

# Update status
order.status = OrderStatus.SUBMITTED
print(order.is_active())  # True

# Check if can cancel
if order.can_cancel():
    order.status = OrderStatus.CANCELLED
```

### 3. Position Model ([position.py](position.py))

Position tracking with PnL calculation.

**Example Usage**:

```python
from core.position import Position
from decimal import Decimal

# Create long position
pos = Position(
    contract="VN30F1M",
    quantity=2,  # Long 2 contracts
    average_price=Decimal("1250.0")
)

# Update unrealized PnL
pos.update_unrealized_pnl(Decimal("1260.0"))
print(pos.unrealized_pnl)  # Decimal('2000')

# Calculate total PnL
pos.realized_pnl = Decimal("500")
pos.total_fees = Decimal("40")
print(pos.total_pnl())  # 500 + 2000 - 40 = 2460

# Check position type
print(pos.is_long())  # True
print(pos.is_flat())  # False
```

### 4. Enumerations ([enums.py](enums.py))

Type-safe enumerations for the trading system.

**Available Enums**:

- `EventType`: MARKET_DATA, SIGNAL, ORDER, FILL, TIME, SYSTEM
- `OrderSide`: BID, ASK
- `OrderStatus`: CREATED, PENDING_SUBMIT, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED

**Example Usage**:

```python
from core.enums import OrderStatus

status = OrderStatus.SUBMITTED

print(status.is_active())  # True
print(status.is_terminal())  # False

status = OrderStatus.FILLED
print(status.is_terminal())  # True
```

## Testing

Run tests with coverage:

```bash
pytest tests/core/ -v --cov=core --cov-report=html
```

**Current Coverage**: 98%

## Design Patterns

### 1. Event-Driven Architecture

Decoupled components communicate through events:
- Components don't directly call each other
- Handlers can be added/removed dynamically
- Exception isolation (one handler failure doesn't affect others)

### 2. Data Classes

Immutable-by-default data structures using Python dataclasses:
- Type hints for all fields
- Auto-generated `__init__`, `__repr__`
- Easy to serialize/deserialize

### 3. State Machine

Order lifecycle follows state machine pattern:
- Valid state transitions enforced
- Helper methods for state queries
- Timestamp tracking for audit trail

## Integration with Trading Components

The core module provides interfaces for trading components:

### OMS (Order Management System)
- Uses `Order` class to track orders
- Subscribes to `SignalEvent` to create orders
- Publishes `OrderEvent` on state changes
- Processes `FillEvent` to update orders

### Portfolio Manager
- Uses `Position` class to track positions
- Subscribes to `FillEvent` to update positions
- Subscribes to `MarketDataEvent` for PnL updates
- Publishes `TimeEvent` for daily settlement

### Risk Manager
- Validates `Order` before submission
- Checks position limits using `Position`
- Enforces margin requirements

## Dependencies

- Python 3.13+
- No external dependencies (uses only standard library)

## Performance

- Event creation: < 1ms
- Event dispatch: < 5ms per handler
- Position PnL update: < 2ms

All operations are fast enough for real-time trading.

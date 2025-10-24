# Engine Module - Trading System Components

The `engine` module provides the core trading system components including Order Management, Portfolio Management, and Risk Management.

## Components

### 1. Order Management System ([oms.py](oms.py))

Complete order lifecycle management with event-driven integration.

#### OrderManager

Central system for creating, submitting, and managing orders.

**Example Usage**:

```python
from decimal import Decimal
from core.event import EventBus, SignalEvent
from core.enums import OrderSide, EventType
from engine.oms import OrderManager

# Create OMS
bus = EventBus()
oms = OrderManager(bus, risk_manager=None)

# Create and submit order
order = oms.create_order(
    contract="VN30F1M",
    side=OrderSide.BID,
    price=Decimal("1250"),
    quantity=1
)
oms.submit_order(order)

# Cancel order
oms.cancel_order(order.order_id)

# Get active orders
active_orders = oms.get_active_orders()
```

**Event Handling**:

```python
# Subscribe to signals for automatic order updates
bus.subscribe(EventType.SIGNAL, oms.on_signal_event)

# Publish signal - OMS automatically cancels old orders and creates new ones
signal = SignalEvent(
    contract="VN30F1M",
    signal_type="UPDATE_BID_ASK",
    bid_price=Decimal("1248"),
    ask_price=Decimal("1253"),
    reason="TIME_ELAPSED"
)
bus.publish(signal)
bus.process_events()

# Now have 2 active orders (bid + ask)
active = oms.get_active_orders_by_contract("VN30F1M")
print(f"Active orders: {len(active)}")  # 2
```

**Order Statistics**:

```python
stats = oms.get_statistics()
print(f"Total orders: {stats['total_orders']}")
print(f"Active: {stats['active_orders']}")
print(f"Filled: {stats['filled_orders']}")
print(f"Cancelled: {stats['cancelled_orders']}")
print(f"Rejected: {stats['rejected_orders']}")
```

**Key Methods**:
- `create_order(contract, side, price, quantity)` - Create new order
- `submit_order(order)` - Submit order after validation
- `cancel_order(order_id)` - Cancel single order
- `cancel_all_orders(contract=None)` - Cancel all or contract-specific orders
- `get_order(order_id)` - Retrieve order by ID
- `get_active_orders()` - Get all active orders
- `get_active_orders_by_contract(contract)` - Filter by contract
- `on_signal_event(event)` - Handle strategy signals
- `on_fill_event(event)` - Process order fills
- `get_statistics()` - Get order statistics

### 2. Portfolio Manager ([portfolio.py](portfolio.py))

Real-time portfolio tracking with PnL calculation and performance metrics.

#### PortfolioManager

Manages all positions, cash, and calculates performance metrics.

**Example Usage**:

```python
from decimal import Decimal
from core.event import EventBus, FillEvent, MarketDataEvent
from core.enums import EventType
from engine.portfolio import PortfolioManager

# Initialize portfolio
bus = EventBus()
portfolio = PortfolioManager(bus, Decimal("500000"))

# Subscribe to events
bus.subscribe(EventType.FILL, portfolio.on_fill_event)
bus.subscribe(EventType.MARKET_DATA, portfolio.on_market_data)

# Process fill
fill = FillEvent(
    order_id="123",
    contract="VN30F1M",
    side="BID",
    fill_price=Decimal("1250"),
    fill_quantity=1,
    fee=Decimal("20")
)
portfolio.on_fill_event(fill)

# Update market price
market_data = MarketDataEvent(
    contract="VN30F1M",
    price=Decimal("1260"),
    bid=Decimal("1259"),
    ask=Decimal("1261"),
    spread=Decimal("2")
)
portfolio.on_market_data(market_data)

# Check position
pos = portfolio.get_position("VN30F1M")
print(f"Quantity: {pos.quantity}")
print(f"Avg Price: {pos.average_price}")
print(f"Unrealized PnL: {pos.unrealized_pnl}")

# Calculate NAV
nav = portfolio.calculate_nav()
print(f"Net Asset Value: {nav}")
```

**Portfolio Summary**:

```python
summary = portfolio.get_summary()
print(f"Cash: {summary['cash']}")
print(f"NAV: {summary['nav']}")
print(f"Total Return: {summary['total_return']}%")

# Position details
for contract, pos_data in summary['positions'].items():
    print(f"{contract}:")
    print(f"  Quantity: {pos_data['quantity']}")
    print(f"  Avg Price: {pos_data['average_price']}")
    print(f"  Unrealized PnL: {pos_data['unrealized_pnl']}")
    print(f"  Realized PnL: {pos_data['realized_pnl']}")
    print(f"  Total PnL: {pos_data['total_pnl']}")
```

**Margin Management**:

```python
# Check available margin for new orders
available = portfolio.get_available_margin("VN30F1M", Decimal("1250"))
print(f"Can place {available} more contracts")

# With 500,000 capital and 1250 price:
# Margin per contract = 1250 * 100 * 0.17 = 21,250
# Available = 500,000 / 21,250 = 23 contracts
```

**Daily Settlement & Performance Metrics**:

```python
from core.event import TimeEvent

# Trigger daily settlement
time_event = TimeEvent(
    event_name="DAILY_SETTLEMENT",
    date=datetime.now()
)
portfolio.on_time_event(time_event)

# Get performance metrics (requires PLUTUS)
metrics = portfolio.get_performance_metrics()
if 'error' not in metrics:
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.4f}")
    print(f"Sortino Ratio: {metrics['sortino_ratio']:.4f}")
    print(f"Max Drawdown: {metrics['maximum_drawdown']:.2%}")
    print(f"Annual Return: {metrics['annual_return']:.2%}")
    print(f"Volatility: {metrics['volatility']:.2%}")
    print(f"VaR 95%: {metrics['value_at_risk_95']:.2%}")
    print(f"CVaR 95%: {metrics['conditional_var_95']:.2%}")
```

**Key Methods**:
- `get_position(contract)` - Get or create position
- `calculate_nav()` - Calculate Net Asset Value
- `get_available_margin(contract, price)` - Calculate available contracts
- `on_fill_event(event)` - Update positions on fills
- `on_market_data(event)` - Update unrealized PnL
- `on_time_event(event)` - Handle daily settlement
- `get_performance_metrics()` - Get PLUTUS metrics
- `get_summary()` - Get portfolio summary

### 3. Risk Manager ([risk.py](risk.py))

Pre-trade risk validation and portfolio monitoring.

#### RiskManager

Validates orders before submission and monitors portfolio health.

**Example Usage**:

```python
from decimal import Decimal
from core.order import Order
from core.enums import OrderSide
from engine.portfolio import PortfolioManager
from engine.risk import RiskManager

# Setup
bus = EventBus()
portfolio = PortfolioManager(bus, Decimal("500000"))
risk = RiskManager(portfolio)

# Validate order
order = Order(
    contract="VN30F1M",
    side=OrderSide.BID,
    price=Decimal("1250"),
    quantity=1
)

if risk.validate_order(order):
    print("Order passed risk checks")
    # Submit order
else:
    print("Order rejected by risk manager")
```

**Validation Checks**:

```python
# Check 1: Margin availability
available = portfolio.get_available_margin("VN30F1M", Decimal("1250"))
if order.quantity > available:
    # Rejected: insufficient margin

# Check 2: Price reasonability
if order.price <= 0:
    # Rejected: invalid price

# Check 3: Quantity validation
if order.quantity <= 0:
    # Rejected: invalid quantity
```

**Portfolio Monitoring**:

```python
# Check if portfolio meets margin requirements
if not risk.check_margin_requirement():
    print("Warning: Margin call!")
    print("Need to liquidate positions")

    # Calculate shortfall
    nav = portfolio.calculate_nav()
    required = sum(
        abs(pos.quantity) * price * Decimal('100') * Decimal('0.17')
        for pos in portfolio.positions.values()
    )
    print(f"NAV: {nav}, Required: {required}")
```

**Integration with OMS**:

```python
# Create OMS with risk manager
oms = OrderManager(bus, risk_manager=risk)

# Orders automatically validated before submission
order = oms.create_order("VN30F1M", OrderSide.BID, Decimal("1250"), 1)
success = oms.submit_order(order)

if not success:
    print(f"Order rejected: {order.status}")
```

**Key Methods**:
- `validate_order(order)` - Pre-trade risk checks
- `check_margin_requirement()` - Portfolio margin validation

---

## Complete System Integration

### Basic Setup

```python
from decimal import Decimal
from core.event import EventBus
from core.enums import EventType
from engine.oms import OrderManager
from engine.portfolio import PortfolioManager
from engine.risk import RiskManager

# 1. Create event bus
bus = EventBus()

# 2. Initialize portfolio
portfolio = PortfolioManager(bus, Decimal("500000"))

# 3. Create risk manager
risk = RiskManager(portfolio)

# 4. Create OMS with risk checks
oms = OrderManager(bus, risk_manager=risk)

# 5. Subscribe to events
bus.subscribe(EventType.SIGNAL, oms.on_signal_event)
bus.subscribe(EventType.FILL, portfolio.on_fill_event)
bus.subscribe(EventType.MARKET_DATA, portfolio.on_market_data)
bus.subscribe(EventType.TIME, portfolio.on_time_event)
```

### Market Making Workflow

```python
from core.event import MarketDataEvent, SignalEvent, FillEvent

# 1. Receive market data
market_data = MarketDataEvent(
    contract="VN30F1M",
    price=Decimal("1250"),
    bid=Decimal("1249"),
    ask=Decimal("1251"),
    spread=Decimal("2")
)
bus.publish(market_data)
bus.process_events()

# 2. Strategy generates signal
signal = SignalEvent(
    contract="VN30F1M",
    signal_type="UPDATE_BID_ASK",
    bid_price=Decimal("1248"),  # Below current price
    ask_price=Decimal("1253"),  # Above current price
    reason="TIME_ELAPSED"
)
bus.publish(signal)
bus.process_events()

# 3. OMS creates and submits orders
active_orders = oms.get_active_orders_by_contract("VN30F1M")
print(f"Active orders: {len(active_orders)}")  # 2 (bid + ask)

# 4. Order gets filled
bid_order = [o for o in active_orders if o.side.value == "BID"][0]
fill = FillEvent(
    order_id=bid_order.order_id,
    contract="VN30F1M",
    side="BID",
    fill_price=Decimal("1248"),
    fill_quantity=1,
    fee=Decimal("20")
)
bus.publish(fill)
bus.process_events()

# 5. Check position and PnL
pos = portfolio.get_position("VN30F1M")
print(f"Position: {pos.quantity}")
print(f"Avg Price: {pos.average_price}")
print(f"Cash: {portfolio.cash}")

# 6. Market moves in our favor
market_data2 = MarketDataEvent(
    contract="VN30F1M",
    price=Decimal("1260")
)
bus.publish(market_data2)
bus.process_events()

print(f"Unrealized PnL: {pos.unrealized_pnl}")  # Profit!

# 7. Daily settlement
from datetime import datetime
from core.event import TimeEvent

time_event = TimeEvent(
    event_name="DAILY_SETTLEMENT",
    date=datetime.now()
)
bus.publish(time_event)
bus.process_events()

# 8. Check performance
summary = portfolio.get_summary()
print(f"Total Return: {summary['total_return']:.2f}%")
```

---

## Design Patterns

### 1. Event-Driven Architecture

All components communicate through events:

```python
# Components don't call each other directly
portfolio.on_fill_event(fill)  # ❌ Bad

# Instead, publish events
bus.publish(fill)
bus.process_events()  # ✅ Good
```

Benefits:
- Loose coupling
- Easy to add new components
- Clear separation of concerns

### 2. Strategy Pattern

Different risk strategies can be swapped:

```python
# Conservative risk
class ConservativeRisk(RiskManager):
    def validate_order(self, order):
        # More strict checks
        pass

# Aggressive risk
class AggressiveRisk(RiskManager):
    def validate_order(self, order):
        # Less strict checks
        pass

# Swap at runtime
oms = OrderManager(bus, risk_manager=ConservativeRisk(portfolio))
```

### 3. Observer Pattern

Event subscriptions follow observer pattern:

```python
# Multiple observers can listen to same event
bus.subscribe(EventType.FILL, portfolio.on_fill_event)
bus.subscribe(EventType.FILL, logger.log_fill)
bus.subscribe(EventType.FILL, analytics.track_fill)
```

---

## Testing

### Unit Tests

```bash
# Run OMS tests
pytest tests/engine/test_oms.py -v

# Run Portfolio tests
pytest tests/engine/test_portfolio.py -v

# Run Risk tests
pytest tests/engine/test_risk.py -v

# Run all engine tests
pytest tests/engine/ -v
```

### Integration Tests

```python
def test_complete_trade_cycle():
    """Test full trading cycle"""
    # Setup
    bus = EventBus()
    portfolio = PortfolioManager(bus, Decimal("500000"))
    risk = RiskManager(portfolio)
    oms = OrderManager(bus, risk_manager=risk)

    # Subscribe
    bus.subscribe(EventType.SIGNAL, oms.on_signal_event)
    bus.subscribe(EventType.FILL, portfolio.on_fill_event)

    # Execute trade cycle
    signal = SignalEvent(...)
    bus.publish(signal)
    bus.process_events()

    # Verify results
    assert len(oms.get_active_orders()) == 2
    assert portfolio.cash < Decimal("500000")
```

**Current Coverage**: 96%

---

## Performance Considerations

### Event Processing

- Events processed in FIFO order
- O(1) event publication
- O(n) event processing where n = number of handlers
- All operations sub-millisecond

### Memory Usage

- Orders stored in dictionaries (O(1) lookup)
- Positions tracked per contract
- Minimal memory overhead

### Optimization Tips

1. **Batch event processing**: Process multiple events at once
2. **Lazy position creation**: Only create Position when needed
3. **Cache market prices**: Avoid redundant calculations

---

## Common Patterns

### Pattern 1: Order Creation and Submission

```python
# Create order
order = oms.create_order(
    contract="VN30F1M",
    side=OrderSide.BID,
    price=Decimal("1250"),
    quantity=1
)

# Submit with automatic risk validation
if oms.submit_order(order):
    print("Order submitted")
else:
    print(f"Order rejected: {order.status}")
```

### Pattern 2: Position Tracking

```python
# Get position (creates if doesn't exist)
pos = portfolio.get_position("VN30F1M")

# Check position state
if pos.is_flat():
    print("No position")
elif pos.is_long():
    print(f"Long {pos.quantity} contracts")
elif pos.is_short():
    print(f"Short {abs(pos.quantity)} contracts")

# Calculate PnL
print(f"Total PnL: {pos.total_pnl()}")
```

### Pattern 3: Risk Management

```python
# Validate before submission
if risk.validate_order(order):
    oms.submit_order(order)
else:
    print("Risk check failed")

# Monitor portfolio health
if not risk.check_margin_requirement():
    # Liquidate positions
    oms.cancel_all_orders()
    # ... liquidation logic
```

---

## Troubleshooting

### Issue 1: Orders Not Created

**Symptom**: Signal published but no orders created

**Solution**: Check event subscription
```python
# Make sure OMS is subscribed
bus.subscribe(EventType.SIGNAL, oms.on_signal_event)
```

### Issue 2: Position Not Updated

**Symptom**: Fill event processed but position unchanged

**Solution**: Check portfolio subscription
```python
# Make sure portfolio is subscribed
bus.subscribe(EventType.FILL, portfolio.on_fill_event)
```

### Issue 3: Order Rejected by Risk

**Symptom**: Orders always rejected

**Solution**: Check margin and capital
```python
# Verify sufficient capital
available = portfolio.get_available_margin(contract, price)
print(f"Available margin: {available} contracts")

# Check portfolio NAV
nav = portfolio.calculate_nav()
print(f"NAV: {nav}")
```

---

## Dependencies

- Python 3.13+
- core module (Event, Order, Position, Enums)
- PLUTUS (optional, for performance metrics)

---

## Next Steps

After mastering the engine module:

1. **Implement Strategy**: Create market making strategy that generates signals
2. **Add Execution Simulator**: Simulate order matching from historical data
3. **Integrate with Data Sources**: Connect to real market data
4. **Deploy Paper Trading**: Run live paper trading system

See [paper-trading-spec.md](../internal-docs/paper-trading-spec.md) for full roadmap.

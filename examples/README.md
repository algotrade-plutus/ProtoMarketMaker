# Examples & Tutorials

This folder contains interactive examples and tutorials for the Paper Trading System.

## Available Notebooks

### 📘 [core-engine-architecture-guide.ipynb](core-engine-architecture-guide.ipynb)

**Comprehensive Phase 1 Tutorial**

A complete guide to the event-driven trading infrastructure covering:

- **Part 1: Core Components**
  - Event system (EventBus, 6 event types)
  - Order model (lifecycle management)
  - Position model (PnL calculation)

- **Part 2: Engine Components**
  - Order Management System (OMS)
  - Portfolio Manager
  - Risk Manager

- **Part 3: Integration Examples**
  - Complete trading system setup
  - Market making simulation
  - Multiple trade cycles

- **Part 4: Advanced Topics**
  - Performance metrics with PLUTUS
  - Error handling
  - Best practices

**Features**:
- ✅ Interactive code examples
- ✅ Step-by-step explanations
- ✅ Complete working simulations
- ✅ Best practices and tips
- ✅ 50+ code cells with outputs

**Usage**:

```bash
# Start Jupyter
cd /Users/dan/algotrade-research/proto/ProtoMarketMaker
source .venv/bin/activate
jupyter notebook examples/core-engine-architecture-guide.ipynb
```

## Prerequisites

- Python 3.13+
- Jupyter Notebook
- All project dependencies installed

```bash
pip install jupyter
pip install -r requirements.txt
```

## Topics Covered

1. **Event-Driven Architecture**
   - Publish-subscribe pattern
   - Event types and handlers
   - Loose coupling benefits

2. **Order Management**
   - Order creation and submission
   - Lifecycle state machine
   - Automatic updates from signals

3. **Portfolio Management**
   - Position tracking
   - Real-time PnL calculation
   - Margin management
   - NAV calculation

4. **Risk Management**
   - Pre-trade validation
   - Margin requirement checks
   - Portfolio health monitoring

5. **Complete Integration**
   - Full system setup
   - Market making workflow
   - Multi-trade simulations

## Learning Path

**Beginner** → Start with Part 1 (Core Components)
- Understand events, orders, and positions
- Run simple examples

**Intermediate** → Move to Part 2 (Engine Components)
- Learn OMS, Portfolio, and Risk management
- Integrate components

**Advanced** → Complete Part 3 & 4
- Build complete trading system
- Implement market making strategy
- Apply best practices

## Interactive Features

The notebook includes:
- 📊 Live portfolio tracking
- 💰 Real-time PnL calculations
- 📈 Market data simulations
- 🔄 Complete trade cycles
- 🛡️ Error handling demonstrations

## Example Outputs

The notebook demonstrates:
- Event publishing and subscription
- Order lifecycle transitions
- Position PnL updates
- Portfolio NAV calculations
- Risk validation results
- Complete market making cycle

## Related Documentation

- [Core Module Guide](../core/README.md)
- [Engine Module Guide](../engine/README.md)
- [Week 1 Report](../markdown-docs/week-1-completion-report.md)
- [Week 2 Report](../markdown-docs/week-2-completion-report.md)
- [Phase 1 Spec](../internal-docs/paper-trading-phase-1-spec.md)

## Extending the Examples

You can extend the notebook with:
- Custom strategy implementations
- Different market scenarios
- Performance analysis
- Risk scenario testing
- Multi-contract portfolios

## Support

For questions or issues:
1. Check the module READMEs
2. Review the completion reports
3. Refer to the specification documents
4. Run the test suite for reference

---

**Happy Learning! 🚀**

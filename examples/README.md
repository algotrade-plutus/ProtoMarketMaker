# Examples & Tutorials

This folder contains interactive examples and tutorials for the Paper Trading System.

## Quick Start

| Notebook | Topics | Complexity |
|----------|--------|------------|
| [core-engine-architecture-guide.ipynb](core-engine-architecture-guide.ipynb) | Event system, OMS, Portfolio, Risk | Beginner |
| [paper-trading-demo.ipynb](paper-trading-demo.ipynb) | Strategy, Execution, Session | Intermediate |
| [redis-streaming-demo.ipynb](redis-streaming-demo.ipynb) | Redis Pub/Sub, Streaming, Monitoring | Advanced |

**Total**: 3 comprehensive notebooks with 110+ interactive code cells

## Python Example Files

| File | Mode | Description | Usage |
|------|------|-------------|-------|
| [playback_mode_example.py](playback_mode_example.py) | Playback | Dual-file historical playback with conditional F2M | `python examples/playback_mode_example.py` |
| [live_mode_example.py](live_mode_example.py) | Live | Real-time trading with contract auto-detection | `python examples/live_mode_example.py` |
| [audit_redis_handler.py](audit_redis_handler.py) | Utility | Redis handler auditing and testing | `python examples/audit_redis_handler.py` |

### Playback Mode Example
**Features:**
- Dual-file historical data playback (separate F1M/F2M)
- Abstract contract symbols (VN30F1M, VN30F2M)
- Conditional F2M subscription during rollover window
- F2M activation/deactivation demonstration
- Performance monitoring (throughput, latency)
- Comprehensive error handling

**Usage:**
```bash
# Basic usage (from project root)
PYTHONPATH=. python examples/playback_mode_example.py

# Prerequisites
redis-server                                           # Start Redis
# Data files required:
#   - data/sample/VN30F1M_rollover.csv (F1M front month)
#   - data/sample/VN30F2M_rollover.csv (F2M second month)
```

### Live Mode Example
**Features:**
- Real-time market data simulation
- Actual contract codes (VN30F2510, VN30F2511, etc.)
- Auto-detection of current front-month contract
- Manual contract specification support
- P&L tracking and performance insights

**Usage:**
```bash
# With auto-detection (detects current F1M/F2M)
PYTHONPATH=. python examples/live_mode_example.py

# With specific contract
PYTHONPATH=. python examples/live_mode_example.py --contract VN30F2511

# Custom duration and capital
PYTHONPATH=. python examples/live_mode_example.py --duration 120 --capital 1000000
```

---

## Available Notebooks

### 📘 [core-engine-architecture-guide.ipynb](core-engine-architecture-guide.ipynb)

**Core Infrastructure Tutorial**

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

---

### 📗 [paper-trading-demo.ipynb](paper-trading-demo.ipynb)

**Strategy & Execution Demo**

A comprehensive demonstration of the paper trading system covering:

- **Part 1: Strategy Engine**
  - Inventory-based market making
  - Time-based vs event-based signals
  - Bid/ask calculation with inventory effects

- **Part 2: Mock Execution Engine**
  - Realistic order fill simulation
  - Fee calculation (20 VND per contract)
  - Complete trading cycle demonstration

- **Part 3: Trading Session**
  - Component orchestration
  - CSV data replay
  - Performance analysis

- **Part 4: Event Flow Visualization**
  - Complete event tracing
  - Market data → Signal → Order → Fill → Portfolio

- **Part 5: Event Recording**
  - Recording events to JSONL
  - Event replay for analysis
  - Event statistics

- **Part 6: Performance Comparison**
  - Testing different step parameters
  - Fill rate analysis
  - Profitability comparison

**Features**:
- ✅ Live trading simulations
- ✅ Event flow tracing
- ✅ Performance comparisons
- ✅ Complete backtest examples
- ✅ Event recording & replay
- ✅ Real-world scenarios

**Usage**:

```bash
# Start Jupyter
cd /Users/dan/algotrade-research/proto/ProtoMarketMaker
source .venv/bin/activate
jupyter notebook examples/paper-trading-demo.ipynb
```

---

### 📙 [redis-streaming-demo.ipynb](redis-streaming-demo.ipynb)

**Redis Streaming & Performance Monitoring**

A comprehensive demonstration of real-time streaming infrastructure covering:

- **Part 1: Redis Connection Test**
  - Verify Redis server availability
  - Check Redis server info and version

- **Part 2: Redis Market Data Handler**
  - Subscribe to Redis Pub/Sub channels
  - Receive and process market data messages
  - EventBus integration

- **Part 3-5: Redis Publisher Modes**
  - Manual message publishing
  - Random walk data generation
  - Sine wave deterministic testing

- **Part 6: Performance Monitor**
  - Real-time trade tracking
  - Fee calculation by contract
  - Metrics calculation

- **Part 7: Redis Trading Session**
  - Complete real-time trading session
  - Health monitoring
  - Session summary and statistics

- **Part 8: Terminal Dashboard**
  - Live dashboard overview (conceptual)
  - Usage examples and CLI commands

- **Part 9: Latency Benchmarking**
  - Measure Redis → EventBus latency
  - Calculate throughput and statistics

- **Part 10: Cleanup**
  - Proper resource cleanup

**Features**:
- ✅ Ultra-low latency (<2ms)
- ✅ High throughput (100+ msg/sec)
- ✅ Real-time monitoring
- ✅ Multiple data generation modes
- ✅ Complete benchmarking
- ✅ Production-ready patterns

**Prerequisites**:
```bash
# Start Redis server
docker run -d -p 6379:6379 redis:latest

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

**Usage**:
```bash
# Start Jupyter
cd /Users/dan/algotrade-research/proto/ProtoMarketMaker
source .venv/bin/activate
jupyter notebook examples/redis-streaming-demo.ipynb
```

---

## Prerequisites

- Python 3.13+
- Jupyter Notebook
- All project dependencies installed
- **Redis server** (for Redis streaming examples)

```bash
# Install Python dependencies
pip install jupyter
pip install -r requirements.txt

# Start Redis (for streaming examples)
docker run -d -p 6379:6379 redis:latest
```

## Topics Covered

### Core Infrastructure

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

### Strategy & Execution

5. **Market-Making Strategy**
   - Inventory-based pricing
   - Time-based signals (every 15 seconds)
   - Event-based signals (on fills)
   - Bid/ask spread management

6. **Order Execution**
   - Realistic fill simulation
   - Price crossing logic
   - Fee calculation and application
   - Order lifecycle completion

7. **Trading Session**
   - Component orchestration
   - CSV data replay
   - Event processing pipeline
   - Results generation

8. **Event Recording & Analysis**
   - JSONL event logging
   - Event replay capabilities
   - Performance tracking
   - Event statistics

9. **Complete Integration**
   - Full system setup
   - End-to-end backtesting
   - Multi-trade simulations
   - Performance optimization

### Streaming & Monitoring

10. **Redis Pub/Sub Streaming**
   - Ultra-low latency message streaming (<2ms)
   - Subscribe to market data channels
   - Background thread listener
   - Auto-reconnect on disconnection

11. **Test Data Publisher**
   - CSV replay at configurable rate
   - Random walk generation
   - Sine wave deterministic testing
   - Multiple contract support

12. **Real-Time Trading Session**
   - Redis-based market data feed
   - Health monitoring and statistics
   - Session lifecycle management
   - Performance summary generation

13. **Performance Monitoring**
   - Live trade tracking
   - Fee calculation by contract
   - Metrics integration with Portfolio
   - Event-driven updates

14. **Terminal Dashboard**
   - Rich-based live UI
   - Session/portfolio/orders panels
   - Redis statistics display
   - Configurable refresh rate

15. **Latency Benchmarking**
   - End-to-end latency measurement
   - Throughput testing (100+ msg/sec)
   - Statistical analysis (mean, p95, p99)
   - Production readiness validation

## Learning Path

### Foundation

**Beginner** → Start with [core-engine-architecture-guide.ipynb](core-engine-architecture-guide.ipynb)
- Part 1: Understand events, orders, and positions
- Part 2: Learn OMS, Portfolio, and Risk management
- Part 3: Integrate components
- Part 4: Apply best practices

### Trading System

**Intermediate** → Move to [paper-trading-demo.ipynb](paper-trading-demo.ipynb)
- Part 1-2: Learn Strategy and Execution engines
- Part 3: Understand Trading Session orchestration
- Part 4: Trace complete event flows

**Advanced** → Complete all demos
- Part 5: Master event recording and replay
- Part 6: Optimize strategy parameters
- Build custom strategies
- Run production-ready backtests

### Real-Time Streaming

**Advanced** → Continue with [redis-streaming-demo.ipynb](redis-streaming-demo.ipynb)
- Part 1-2: Understand Redis Pub/Sub and market data streaming
- Part 3-5: Learn different data generation modes
- Part 6: Master performance monitoring
- Part 7: Build real-time trading sessions

**Expert** → Master production deployment
- Part 8: Deploy terminal dashboard
- Part 9: Optimize for low latency
- Part 10: Production-ready cleanup
- Integrate with live data feeds
- Scale to multiple contracts

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

### Core Infrastructure Documentation
- [Core Module Guide](../core/README.md)
- [Engine Module Guide](../engine/README.md)

### Strategy & Execution Documentation
- [Paper Trading Session Guide](../paper_trading/)
- [CLI Usage](../paper_trading/main.py)

### Redis Streaming Documentation
- [Redis Stream Handler](../data/redis_stream.py)
- [Redis Publisher Tool](../tools/redis_publisher.py)
- [Performance Monitor](../evaluation/monitor.py)
- [Terminal Dashboard](../evaluation/dashboard.py)

### Overall Project
- [Project README](../README.md)

## Extending the Examples

### Core Infrastructure Extensions
- Custom event types
- Additional risk checks
- Custom portfolio metrics
- Multi-contract portfolios
- Different position sizing

### Strategy & Execution Extensions
- Custom strategy implementations
- Alternative execution models
- Different market scenarios
- Parameter optimization
- Performance analysis
- Real-time data streaming
- Multiple strategy comparison
- Event-based backtesting

### Redis Streaming Extensions
- Custom Redis message formats
- Alternative streaming backends (Kafka, NATS)
- Web-based dashboard (Flask/FastAPI)
- Database persistence for trades
- Email/Slack alerting
- Multi-strategy monitoring
- Advanced latency optimization
- Production deployment patterns
- Horizontal scaling
- Circuit breaker patterns

## Support

For questions or issues:
1. Check the module READMEs
2. Review the completion reports
3. Refer to the specification documents
4. Run the test suite for reference

---

## Archived Files

The `archive/` folder contains debug and testing scripts that were used during development:
- `debug_engine_consumer.py` - Engine debugging script
- `debug_redis_consumer.py` - Redis consumer debugging
- `simple_redis_consumer.py` - Simple Redis test consumer
- `simple_redis_publisher.py` - Simple Redis test publisher
- `test_dual_file_publishing.py` - Dual-file publishing test

These files are preserved for reference but are not part of the main examples. For production use, refer to the comprehensive example files and Jupyter notebooks listed above.

---

**Happy Learning! 🚀**

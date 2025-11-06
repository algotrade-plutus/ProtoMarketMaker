# Paper Trading Module

**Status**: Production-ready Redis-based paper trading with automatic contract resolution

---

## Overview

The paper trading module provides a complete simulation environment for testing trading strategies with real-time or historical data, without risking actual capital. It supports both CSV file playback and Redis streaming for realistic market data simulation.

### Key Features

- **Contract Symbol Resolution**: Automatic detection of VN30 futures contract codes (F1M/F2M → actual symbols)
- **Redis Streaming**: Real-time market data via Redis Pub/Sub
- **Event-Driven Architecture**: Full integration with all trading components
- **Performance Monitoring**: Live metrics, trade tracking, and PLUTUS integration
- **Results Export**: JSON serialization and comprehensive reporting
- **Two Deployment Modes**: Local testing (CSV playback) and production (live feeds)

---

## Architecture

```
RedisPaperTradingEngine
  ├── EventBus (core messaging)
  ├── ContractSymbolResolver (F1M/F2M detection)
  ├── RedisMarketDataHandler (streaming data)
  ├── PortfolioManager (positions, NAV, PLUTUS)
  ├── RiskManager (pre-trade validation)
  ├── OrderManager (OMS)
  ├── MarketMakerStrategy (signal generation)
  ├── MockExecutionEngine (order matching)
  └── PerformanceMonitor (trade statistics)
```

**100% Component Reuse**: All trading components are reused. Only Redis data feed is swapped for real-time data.

---

## Quick Start

### Prerequisites

```bash
# 1. Redis server running
redis-server

# Verify connection
redis-cli ping  # Should return "PONG"

# 2. Python environment activated
source .venv/bin/activate

# 3. Dependencies installed
pip install -r requirements.txt
```

### Basic Usage

#### 1. CLI Runner (Recommended)

```bash
# Run with default configuration
python -m paper_trading.runner

# Run for specific duration
python -m paper_trading.runner --duration 300  # 5 minutes

# Export results to JSON
python -m paper_trading.runner --output results/session_$(date +%Y%m%d_%H%M%S).json

# Disable confirmation prompt (for automation)
python -m paper_trading.runner --no-confirm

# Override contracts
python -m paper_trading.runner --contracts VN30F2510 VN30F2511
```

#### 2. Programmatic Usage

```python
from decimal import Decimal
from paper_trading.engine import RedisPaperTradingEngine

# Create engine
engine = RedisPaperTradingEngine(
    initial_capital=Decimal('500000'),
    step=Decimal('2.9'),
    redis_host='localhost',
    redis_port=6379,
    contracts=['VN30F1M', 'VN30F2M']  # Auto-resolves to actual codes
)

# Mode 1: Blocking run for specific duration
results = engine.run(duration_seconds=3600)  # 1 hour
results.print_summary()
results.to_json('results/session.json')

# Mode 2: Non-blocking start/stop
engine.start()

# Monitor in real-time
while True:
    summary = engine.get_summary()
    print(f"NAV: {summary['current_nav']:,.0f} | Trades: {summary['total_trades']}")
    time.sleep(5)

    # Stop condition
    if some_condition:
        break

results = engine.stop()
```

---

## Configuration

### Config File: `config/redis_config.json`

```json
{
  "redis_host": "localhost",
  "redis_port": 6379,
  "channel_prefix": "market",
  "contracts": ["VN30F1M", "VN30F2M"],
  "auto_detect_contracts": true,
  "contract_mappings": {},
  "confirm_symbols": true,
  "initial_capital": 500000,
  "step": 2.9,
  "update_interval_seconds": 15,
  "record_events": false,
  "event_log_path": "logs/paper_trading/events.jsonl"
}
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `redis_host` | string | `"localhost"` | Redis server hostname |
| `redis_port` | integer | `6379` | Redis server port |
| `channel_prefix` | string | `"market"` | Redis channel prefix (format: `{prefix}:{contract}`) |
| `contracts` | array | `["VN30F1M"]` | List of contracts (informal or actual codes) |
| `auto_detect_contracts` | boolean | `true` | Auto-detect F1/F2 actual codes based on expiration |
| `contract_mappings` | object | `{}` | Manual symbol mappings (when `auto_detect=false`) |
| `confirm_symbols` | boolean | `true` | Prompt user to confirm resolved symbols |
| `initial_capital` | number | `500000` | Starting capital in VND |
| `step` | number | `2.9` | Market maker step parameter |
| `update_interval_seconds` | integer | `15` | Time-based signal interval |
| `record_events` | boolean | `false` | Enable JSONL event logging |
| `event_log_path` | string | `"logs/..."` | Path to event log file |

### Environment Variable Overrides

```bash
# Override Redis connection
export REDIS_HOST="192.168.1.100"
export REDIS_PORT="6380"

python -m paper_trading.runner
```

---

## Contract Symbol Resolution

### The Problem

Vietnamese futures data providers use **exact month codes** (VN30F2510, VN30F2511) that follow expiration rules. The informal symbols VN30F1M and VN30F2M **do not exist** in most real-time APIs.

**User feedback**: *"Many many bugs in the live system came from the wrong tickersymbol of F1 and F2."*

### The Solution

**Automatic Detection** (recommended):

```python
from utils.contract_resolver import ContractSymbolResolver

resolver = ContractSymbolResolver()  # auto_detect=True

# Automatically calculates current F1/F2 based on third Thursday rule
f1_code = resolver.resolve('VN30F1M')  # → 'VN30F2510' on Oct 15, 2025
f2_code = resolver.resolve('VN30F2M')  # → 'VN30F2511' on Oct 15, 2025

# Get expiration details
summary = resolver.get_resolution_summary(['VN30F1M', 'VN30F2M'])
# {
#   'VN30F1M': {
#     'code': 'VN30F2510',
#     'expiration': date(2025, 10, 16),  # Third Thursday
#     'days_to_expiry': 1
#   },
#   ...
# }
```

**Manual Override** (for historical data):

```python
# For testing with historical data (Feb 2022)
resolver = ContractSymbolResolver(
    auto_detect=False,
    contract_mappings={
        'VN30F1M': 'VN30F2202',
        'VN30F2M': 'VN30F2203'
    }
)
```

### Expiration Rule

VN30 futures contracts expire on the **third Thursday of each month**:

```python
# February 2025 example:
# Thu Feb 6  (first Thursday)
# Thu Feb 13 (second Thursday)
# Thu Feb 20 (EXPIRATION - third Thursday)
# Thu Feb 27 (fourth Thursday)
```

### Safety Confirmation

CLI runner displays resolved symbols and waits for confirmation:

```
🔍 Contract Symbol Resolution:
   VN30F1M → VN30F2510 (expires Oct 16, 2025, 1 days)
   VN30F2M → VN30F2511 (expires Nov 20, 2025, 36 days)

⚠️  Please verify ticker symbols are correct.
Proceed with trading? [Y/n]:
```

**Disable for automation**: Use `--no-confirm` flag or set `confirm_symbols: false` in config.

---

## Testing with Historical Data

### Step 1: Start Redis Publisher

```bash
# Terminal 1: Publish historical CSV data
python -m tools.redis_publisher \
  --csv data/sample/merged_is_data_1day.csv \
  --rate 10 \
  --channel-prefix market
```

### Step 2: Configure for Historical Contracts

Edit `config/redis_config.json`:

```json
{
  "redis_host": "localhost",
  "redis_port": 6379,
  "channel_prefix": "market",
  "contracts": ["VN30F2202", "VN30F2203"],
  "auto_detect_contracts": false,
  "contract_mappings": {
    "VN30F1M": "VN30F2202",
    "VN30F2M": "VN30F2203"
  },
  "confirm_symbols": true,
  "initial_capital": 500000,
  "step": 2.9,
  "update_interval_seconds": 15,
  "record_events": true,
  "event_log_path": "logs/paper_trading/historical_replay.jsonl"
}
```

### Step 3: Run Paper Trading

```bash
# Terminal 2: Run paper trading
python -m paper_trading.runner \
  --duration 180 \
  --output results/historical_test.json
```

### Step 4: Analyze Results

```bash
# View results
cat results/historical_test.json | jq .

# View event log (if recorded)
cat logs/paper_trading/historical_replay.jsonl | jq .
```

---

## Results Analysis

### PaperTradingResults Object

```python
@dataclass
class PaperTradingResults:
    # Session metadata
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    mode: str  # "redis"

    # Performance metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    hpr: float

    # Trading statistics
    total_trades: int
    buy_trades: int
    sell_trades: int
    total_fees: Decimal

    # Portfolio data
    initial_capital: Decimal
    final_nav: Decimal
    daily_nav: List[Decimal]
    daily_returns: List[Decimal]
    tracking_dates: List[date]

    # Redis metrics
    messages_received: int
    messages_processed: int
    avg_latency_ms: float
    reconnect_count: int

    # Contract rollovers
    rollovers: List[dict]
```

### Export Methods

```python
# Print to console
results.print_summary()

# Export to JSON
results.to_json('results/session.json')

# Load from JSON
results = PaperTradingResults.from_json('results/session.json')
```

### JSON Structure

```json
{
  "session": {
    "start_time": "2025-11-03T14:30:00",
    "end_time": "2025-11-03T14:33:00",
    "duration_seconds": 180.5,
    "mode": "redis"
  },
  "performance": {
    "sharpe_ratio": 0.6543,
    "sortino_ratio": 0.9821,
    "max_drawdown": -0.0008,
    "hpr": 0.0024,
    "initial_capital": "500000.00",
    "final_nav": "501200.00"
  },
  "trading": {
    "total_trades": 6,
    "buy_trades": 3,
    "sell_trades": 3,
    "total_fees": "360.00"
  },
  "redis_metrics": {
    "messages_received": 1800,
    "messages_processed": 1800,
    "avg_latency_ms": 28.5,
    "reconnect_count": 0
  },
  "portfolio_timeline": {
    "daily_nav": [...],
    "daily_returns": [...],
    "tracking_dates": [...]
  },
  "rollovers": []
}
```

---

## Performance Benchmarks

### Target Metrics

- **Throughput**: ≥50 messages/second
- **Latency**: <50ms average
- **Processing Rate**: ≥90% (messages processed / messages received)
- **Reliability**: Zero reconnects under normal conditions

### Running Benchmarks

```bash
# Integration tests include benchmarks
pytest tests/integration/test_paper_trading_integration.py::TestPaperTradingPerformance -v
```

### Expected Results

```
THROUGHPUT BENCHMARK
============================================================
Messages published:  500
Messages processed:  485
Processing rate:     97.0%
Throughput:          161.7 msg/s
Avg latency:         15.32 ms
============================================================

✅ Processing rate: EXCELLENT (≥90%)
✅ Throughput: EXCELLENT (≥50 msg/s)
✅ Latency: EXCELLENT (<50ms)
```

---

## Production Deployment

### Two-Parameter Switch

**Local Testing**:
```json
{
  "redis_host": "localhost",
  "redis_port": 6379
}
```

**Production**:
```json
{
  "redis_host": "192.168.1.100",  // Production Redis server
  "redis_port": 6379
}
```

### Production Checklist

- [ ] Redis server configured and accessible
- [ ] Contract symbol resolution tested and verified
- [ ] Safety confirmation enabled (`confirm_symbols: true`)
- [ ] Event logging enabled for audit trail
- [ ] Monitoring dashboard deployed (optional)
- [ ] Results export path configured
- [ ] Error alerting configured
- [ ] Backup and recovery procedures documented

### Automation Mode

For automated deployments (no user interaction):

```bash
# Disable confirmation prompts
python -m paper_trading.runner --no-confirm --duration 86400  # 24 hours

# Or in config
{
  "confirm_symbols": false
}
```

---

## Troubleshooting

### Problem: "Failed to subscribe to VN30F2510"

**Solution**: Verify Redis publisher is running and using correct channel prefix

```bash
# Check Redis channels
redis-cli PUBSUB CHANNELS

# Subscribe manually to test
redis-cli SUBSCRIBE market:VN30F2510
```

### Problem: "No messages received"

**Solution**: Check publisher playback rate and CSV file

```bash
# Monitor Redis commands in real-time
redis-cli MONITOR

# Verify publisher is sending data
python -m tools.redis_publisher --csv data/sample/merged_is_data_1day.csv --rate 10
```

### Problem: "Contract code format error"

**Solution**: Ensure contract_mappings match actual CSV contract codes

```bash
# Check CSV ticker symbols
head -1 data/sample/merged_is_data_1day.csv
# Should contain columns with VN30F2202, VN30F2203, etc.
```

### Problem: "High latency (>100ms)"

**Solutions**:
1. Reduce publisher rate: `--rate 10` instead of `--rate 100`
2. Check Redis server load: `redis-cli INFO`
3. Use localhost for testing (not remote Redis)
4. Check network latency if using remote Redis

### Problem: "Wrong expiration date detected"

**Solution**: Verify system date is correct and contract resolver logic

```python
from utils.contract_resolver import ContractSymbolResolver
from datetime import date

resolver = ContractSymbolResolver()

# Check current date
print(f"Current date: {date.today()}")

# Check F1 expiration
f1_code = resolver.resolve('VN30F1M')
f1_exp = resolver.get_expiration_date(f1_code)
print(f"F1: {f1_code} expires {f1_exp}")

# Manually verify third Thursday
# Use calendar or: python -c "import calendar; print(calendar.month(2025, 10))"
```

---

## Advanced Usage

### Custom Update Interval

```python
# Fast updates (every 5 seconds)
engine = RedisPaperTradingEngine(
    initial_capital=Decimal('500000'),
    step=Decimal('2.9'),
    update_interval_seconds=5  # More frequent signals
)
```

### Event Recording

```python
# Enable event logging for debugging
engine = RedisPaperTradingEngine(
    initial_capital=Decimal('500000'),
    step=Decimal('2.9'),
    record_events=True,
    event_log_path='logs/paper_trading/debug_session.jsonl'
)
```

**Event log format** (JSONL - one JSON object per line):

```json
{"type": "MARKET_DATA", "timestamp": "2025-11-03T14:30:00", "contract": "VN30F2510", "price": 1250.0}
{"type": "SIGNAL", "timestamp": "2025-11-03T14:30:15", "contract": "VN30F2510", "side": "BUY"}
{"type": "ORDER_PLACED", "timestamp": "2025-11-03T14:30:15", "order_id": "ORD001", "contract": "VN30F2510"}
{"type": "FILL", "timestamp": "2025-11-03T14:30:16", "order_id": "ORD001", "price": 1250.5, "quantity": 1}
```

### Real-Time Monitoring

```python
import time
from paper_trading.engine import RedisPaperTradingEngine

engine = RedisPaperTradingEngine(...)
engine.start()

try:
    while True:
        summary = engine.get_summary()

        print(f"[{time.strftime('%H:%M:%S')}] "
              f"NAV: {summary['current_nav']:>10,.0f} | "
              f"PnL: {summary['pnl']:>+8,.0f} | "
              f"Trades: {summary['total_trades']:>3} | "
              f"Latency: {summary['redis_latency_ms']:>5.1f}ms")

        time.sleep(5)
except KeyboardInterrupt:
    print("\nStopping...")
    results = engine.stop()
    results.print_summary()
```

---

## Module Components

### `engine.py` - RedisPaperTradingEngine

Main orchestration class that coordinates all trading components.

**Key Methods**:
- `start()`: Start non-blocking execution
- `stop()`: Stop and return results
- `run(duration_seconds)`: Blocking execution for specific duration
- `get_summary()`: Real-time status and metrics

### `results.py` - PaperTradingResults

Results storage and serialization.

**Key Methods**:
- `to_json(path)`: Export to JSON file
- `from_json(path)`: Load from JSON file
- `print_summary()`: Display formatted summary

### `runner.py` - CLI Runner

Command-line interface with contract resolution.

**Usage**:
```bash
python -m paper_trading.runner [OPTIONS]
```

**Options**:
- `--duration SECONDS`: Session duration
- `--contracts CODES`: Override contracts
- `--output PATH`: Export results to JSON
- `--no-confirm`: Disable confirmation prompt
- `--record-events`: Enable event logging
- `--event-log PATH`: Custom event log path

---

## Integration with Other Modules

### With Core & Engine

```python
from core.event import EventBus, EventType
from engine.portfolio import PortfolioManager
from engine.oms import OrderManager

# All core components are orchestrated by RedisPaperTradingEngine
```

### With Redis Streaming

```python
from data.redis_stream import RedisMarketDataHandler

# RedisPaperTradingEngine uses RedisMarketDataHandler for streaming
```

### With Ground Truth

```bash
# Compare paper trading results with ground truth
python -m paper_trading.runner \
  --contracts VN30F2202 VN30F2203 \
  --duration 180 \
  --output results/paper_trading_1day.json

# Compare with ground truth log
diff logs/paper_trading/events.jsonl logs/ground_truth/iterative_1day.log
```

---

## Testing

### Unit Tests

```bash
# Test contract resolver
pytest tests/utils/test_contract_resolver.py -v

# Test results dataclass
pytest tests/paper_trading/test_results.py -v

# Test engine
pytest tests/paper_trading/test_engine.py -v
```

### Integration Tests

```bash
# Run all integration tests (requires Redis)
pytest tests/integration/test_paper_trading_integration.py -v

# Run specific test
pytest tests/integration/test_paper_trading_integration.py::TestPaperTradingIntegration::test_basic_connection_and_subscription -v

# Run performance benchmarks
pytest tests/integration/test_paper_trading_integration.py::TestPaperTradingPerformance -v
```

### Test Coverage

```bash
pytest tests/utils/test_contract_resolver.py \
       tests/paper_trading/test_results.py \
       tests/paper_trading/test_engine.py \
       --cov=utils.contract_resolver \
       --cov=paper_trading.results \
       --cov=paper_trading.engine \
       --cov-report=html
```

---

## Examples

### Example 1: Basic Local Test

```python
from decimal import Decimal
from paper_trading.engine import RedisPaperTradingEngine

# Simple 5-minute test
engine = RedisPaperTradingEngine(
    initial_capital=Decimal('500000'),
    step=Decimal('2.9')
)

results = engine.run(duration_seconds=300)
results.print_summary()
```

### Example 2: Historical CSV Playback

```bash
# Terminal 1: Publish CSV
python -m tools.redis_publisher --csv data/sample/merged_is_data_1day.csv --rate 50

# Terminal 2: Run paper trading
python -m paper_trading.runner --duration 180 --output results/1day_replay.json
```

### Example 3: Production Monitoring

```python
from decimal import Decimal
from paper_trading.engine import RedisPaperTradingEngine
import time

# Production configuration
engine = RedisPaperTradingEngine(
    initial_capital=Decimal('500000'),
    step=Decimal('2.9'),
    redis_host='192.168.1.100',  # Production Redis
    redis_port=6379,
    contracts=['VN30F1M', 'VN30F2M'],
    record_events=True,
    event_log_path='/var/log/trading/paper_trading.jsonl'
)

engine.start()

# Monitor for 24 hours
end_time = time.time() + 86400

while time.time() < end_time:
    summary = engine.get_summary()

    # Alert on anomalies
    if summary['redis_latency_ms'] > 100:
        print(f"⚠️  High latency: {summary['redis_latency_ms']:.1f}ms")

    if summary['current_nav'] < summary['initial_nav'] * 0.95:
        print(f"⚠️  Significant drawdown: {summary['return_pct']:.2f}%")

    time.sleep(60)

results = engine.stop()
results.to_json('/var/log/trading/session_results.json')
```

---

## API Reference

See also:
- [Contract Resolver API](../utils/contract_resolver.py)
- [Results API](results.py)
- [Engine API](engine.py)
- [Runner CLI](runner.py)

---

## Additional Resources

- **Jupyter Tutorial**: `examples/phase-5-redis-paper-trading-demo.ipynb`
- **Integration Tests**: `tests/integration/test_paper_trading_integration.py`
- **Redis Publisher**: `tools/redis_publisher.py`

---

## Support

For issues, questions, or contributions:
- Run integration tests to verify setup
- Review event logs for debugging
- Check [README.md](../README.md) for project documentation

---

**Last Updated**: November 3, 2025

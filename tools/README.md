# Tools Directory

This directory contains utility scripts and tools for the ProtoMarketMaker project.

## Verification Scripts

These scripts help you verify your connections and configurations before running the paper trading system.

### 1. Redis Connection Verification

**Purpose**: Test Redis connection, Pub/Sub functionality, contract resolution, and market data streaming.

**Usage**:
```bash
# Run from project root
python -m tools.verify_redis_connection

# Or make executable and run directly
chmod +x tools/verify_redis_connection.py
./tools/verify_redis_connection.py
```

**What it tests**:
- ✅ Basic Redis connection (PING, SET/GET)
- ✅ Pub/Sub functionality
- ✅ Contract symbol resolution (VN30F1M → VN30F2511, etc.)
- ✅ Market data streaming (subscribe to live feeds)
- 📊 Server info and statistics

**Configuration**: Reads from `.env.redis` and `config/redis_config.json`

**Output**: Creates detailed log file `test_redis_YYYYMMDD_HHMMSS.log`

---

### 2. PaperBroker FIX Connection Verification

**Purpose**: Test connection to PaperBroker FIX server with detailed diagnostics.

**Usage**:
```bash
# Run from project root
python -m tools.verify_paperbroker_connection

# Or make executable and run directly
chmod +x tools/verify_paperbroker_connection.py
./tools/verify_paperbroker_connection.py
```

**What it tests**:
- ✅ Environment variable validation
- ✅ FIX server connectivity
- ✅ Authentication (username/password)
- ✅ Session establishment (logon)
- 📊 Connection status and diagnostics

**Configuration**: Reads from `.env.paperbroker`

**Required environment variables**:
- `PAPERBROKER_FIX_HOST` - FIX server hostname
- `PAPERBROKER_FIX_PORT` - FIX server port
- `PAPERBROKER_SENDER_COMP_ID` - Sender CompID
- `PAPERBROKER_TARGET_COMP_ID` - Target CompID
- `PAPERBROKER_FIX_USERNAME` - FIX username
- `PAPERBROKER_FIX_PASSWORD` - FIX password

**Optional variables**:
- `PAPERBROKER_REST_BASE_URL` - REST API URL
- `PAPERBROKER_SUB_ACCOUNT` - Sub-account ID (default: D1)

**Output**: Creates detailed log file `test_connection_YYYYMMDD_HHMMSS.log`

---

### 3. Sample Data Integrity Verification

**Purpose**: Verify integrity of sample CSV data files used for backtesting.

**Usage**:
```bash
# Run from project root
python -m tools.verify_sample_data_integrity
```

**What it checks**:
- ✅ File existence and readability
- ✅ CSV structure and columns
- ✅ Data types and format
- ✅ Date ranges and completeness
- ✅ Missing values and data quality

---

## Data Publishing Tools

### 4. Redis Market Data Publisher

**Purpose**: Publish historical market data to Redis for testing and playback.

**Usage**:
```bash
# Publish from CSV file
python -m tools.redis_publisher \
    --csv data/sample/merged_is_data_1day.csv \
    --rate 10

# Publish dual-file (F1M + F2M)
python -m tools.redis_publisher \
    --f1m-csv data/sample/VN30F1M_1day.csv \
    --f2m-csv data/sample/VN30F2M_1day.csv \
    --rate 50
```

**Options**:
- `--csv` - Single merged CSV file
- `--f1m-csv` / `--f2m-csv` - Separate F1M and F2M files
- `--rate` - Publishing rate in Hz (default: 10)
- `--redis-host` - Redis host (default: localhost)
- `--redis-port` - Redis port (default: 6379)
- `--channel-prefix` - Channel prefix (default: market)

---

## Sample Data Creation Tools

### 5. Create All Dual-File Samples

**Purpose**: Extract dual-file samples (F1M + F2M) from merged historical data.

**Usage**:
```bash
python -m tools.create_all_dual_file_samples
```

**Output**: Creates 14 CSV files (7 pairs) in `data/sample/`:
- VN30F1M_1day.csv / VN30F2M_1day.csv
- VN30F1M_2day.csv / VN30F2M_2day.csv
- ... (and more time periods)

---

### 6. Create Sample Data from Merged

**Purpose**: Extract specific time period samples from merged historical data.

**Usage**:
```bash
python -m tools.create_sample_data_from_merged
```

**Output**: Creates sample CSV files in `data/sample/` directory

---

## Ground Truth Testing Tools

### 7. Run Ground Truth Tests

**Purpose**: Run reference backtests to establish authoritative baseline results.

**Usage**:
```bash
python -m tools.run_ground_truth_tests
```

**Output**:
- Comprehensive logs in `logs/ground_truth/`
- Summary report with NAV, HPR, signals, fills

---

## Troubleshooting

### Redis Connection Issues

If `verify_redis_connection` fails:

1. **Check Redis is running**:
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

2. **Check configuration**:
   - Verify `.env.redis` has correct host/port
   - Check `config/redis_config.json` settings

3. **Test basic connectivity**:
   ```bash
   redis-cli -h localhost -p 6379 ping
   ```

### PaperBroker Connection Issues

If `verify_paperbroker_connection` fails:

1. **Check environment variables**:
   ```bash
   cat .env.paperbroker
   # Verify all required variables are set
   ```

2. **Test network connectivity**:
   ```bash
   telnet <FIX_HOST> <FIX_PORT>
   # Should establish connection
   ```

3. **Common issues**:
   - Incorrect credentials → Check username/password
   - CompID mismatch → Verify sender/target CompIDs
   - Server down → Contact administrator

---

## Running from Project Root

All tools are designed to be run from the project root directory:

```bash
cd /path/to/ProtoMarketMaker

# Run verification scripts
python -m tools.verify_redis_connection
python -m tools.verify_paperbroker_connection

# Run data tools
python -m tools.redis_publisher --csv data/sample/merged_is_data_1day.csv

# Run testing tools
python -m tools.run_ground_truth_tests
```

---

## Development

When adding new tools to this directory:

1. Add proper docstrings and help text
2. Use absolute imports from project root
3. Accept configuration via environment variables or command-line args
4. Provide detailed logging and error messages
5. Update this README with usage instructions

---

## Support

For issues or questions:
- Check logs in the project root (test_*.log files)
- Review troubleshooting guides in `internal-docs/`
- See main project README for additional documentation

# Contract Symbol Resolution Guide

## Overview

ProtoMarketMaker supports flexible contract symbol resolution to handle Vietnamese VN30 futures contracts. You can use abstract symbols (VN30F1M, VN30F2M) that automatically resolve to actual exchange codes (VN30F2511, VN30F2512).

## Current Configuration Status

### Your Setup (Working ✅)

```
Input Symbols:    VN30F1M, VN30F2M
Resolved To:      VN30F2511, VN30F2512
Channel Prefix:   HNXDS
Final Channels:   HNXDS:VN30F2511, HNXDS:VN30F2512

Expiration Dates:
  VN30F2511: November 20, 2025 (7 days remaining)
  VN30F2512: December 18, 2025 (35 days remaining)
```

## Configuration Files

### 1. `.env.redis` (Highest Priority - RECOMMENDED)

You can now configure everything in `.env.redis` without needing the JSON file:

```bash
# Redis Connection
REDIS_HOST=<host>
REDIS_PORT=<port>
REDIS_PASSWORD=<password>
REDIS_DB=<db>
REDIS_DECODE_RESPONSES=<boolean>

# Channel Configuration
REDIS_CHANNEL_PREFIX=<prefix>

# Contract Configuration
REDIS_CONTRACTS=VN30F1M,VN30F2M
AUTO_DETECT_CONTRACTS=false

# Contract Mappings (JSON format)
CONTRACT_MAPPINGS={"VN30F1M":"VN30F2511","VN30F2M":"VN30F2512"}
```

**Advantages:**
- ✅ Single configuration file for everything
- ✅ No need to edit `redis_config.json`
- ✅ Settings override JSON file
- ✅ Easy to version control (gitignored by default)

### 2. `config/redis_config.json` (Lower Priority - OPTIONAL)

Alternatively, you can use the JSON file for contract configuration:

```json
{
  "redis_host": "localhost",
  "redis_port": 6379,
  "contracts": ["VN30F1M", "VN30F2M"],
  "auto_detect_contracts": false,
  "contract_mappings": {
    "VN30F1M": "VN30F2511",
    "VN30F2M": "VN30F2512"
  },
  "channel_prefix": "market"
}
```

**Note:** Settings in `.env.redis` override `redis_config.json`. You only need the JSON file if you prefer JSON format or want to share configuration across environments.

## Resolution Modes

### Mode 1: Manual Mappings (Current - Recommended for Production)

**When:** You know the exact contract codes and trading months

**Setup Option A - .env.redis (Recommended):**
```bash
REDIS_CONTRACTS=VN30F1M,VN30F2M
AUTO_DETECT_CONTRACTS=false
CONTRACT_MAPPINGS={"VN30F1M":"VN30F2511","VN30F2M":"VN30F2512"}
```

**Setup Option B - redis_config.json:**
```json
{
  "contracts": ["VN30F1M", "VN30F2M"],
  "auto_detect_contracts": false,
  "contract_mappings": {
    "VN30F1M": "VN30F2511",
    "VN30F2M": "VN30F2512"
  }
}
```

**Result:**
- `VN30F1M` → `VN30F2511` (explicit mapping)
- `VN30F2M` → `VN30F2512` (explicit mapping)
- Channels: `HNXDS:VN30F2511`, `HNXDS:VN30F2512`

**Advantages:**
- ✅ Explicit control over contract codes
- ✅ No risk of wrong auto-detection
- ✅ Works perfectly with external Redis feeds

**Update Monthly:** Change mappings when contracts roll over (third Thursday)

---

### Mode 2: Pure Auto-Detection

**When:** You want automatic resolution based on current date

**Setup Option A - .env.redis (Recommended):**
```bash
REDIS_CONTRACTS=VN30F1M,VN30F2M
AUTO_DETECT_CONTRACTS=true
CONTRACT_MAPPINGS=
```

**Setup Option B - redis_config.json:**
```json
{
  "contracts": ["VN30F1M", "VN30F2M"],
  "auto_detect_contracts": true,
  "contract_mappings": {}
}
```

**Result:**
- `VN30F1M` → Auto-detects current front month (e.g., `VN30F2511` in Nov 2025)
- `VN30F2M` → Auto-detects second month (e.g., `VN30F2512` in Nov 2025)
- Automatically rolls over on third Thursday

**Advantages:**
- ✅ No monthly updates needed
- ✅ Automatic rollover handling

**Disadvantages:**
- ⚠️ May mismatch with external feed if they use different naming

---

### Mode 3: Abstract Symbols Only

**When:** External feed uses abstract symbols like `VN30F1M` directly

**Setup Option A - .env.redis (Recommended):**
```bash
REDIS_CONTRACTS=VN30F1M,VN30F2M
AUTO_DETECT_CONTRACTS=false
CONTRACT_MAPPINGS={"VN30F1M":"VN30F1M","VN30F2M":"VN30F2M"}
```

**Setup Option B - redis_config.json:**
```json
{
  "contracts": ["VN30F1M", "VN30F2M"],
  "auto_detect_contracts": false,
  "contract_mappings": {
    "VN30F1M": "VN30F1M",
    "VN30F2M": "VN30F2M"
  }
}
```

**Result:**
- `VN30F1M` → `VN30F1M` (no translation)
- `VN30F2M` → `VN30F2M` (no translation)
- Channels: `HNXDS:VN30F1M`, `HNXDS:VN30F2M`

---

## Channel Prefix Configuration

The channel prefix determines the Redis Pub/Sub channel structure:

### Option 1: HNXDS Prefix (Your Current Setup)

```bash
REDIS_CHANNEL_PREFIX=HNXDS
```

**Channels:**
- `HNXDS:VN30F2511`
- `HNXDS:VN30F2512`

### Option 2: Market Prefix (Default)

```bash
REDIS_CHANNEL_PREFIX=market
```

**Channels:**
- `market:VN30F2511`
- `market:VN30F2512`

### Option 3: No Prefix

```bash
REDIS_CHANNEL_PREFIX=
```

**Channels:**
- `VN30F2511`
- `VN30F2512`

## Testing Your Configuration

Run the test script to verify your setup:

```bash
source .venv/bin/activate
python test_redis_connection.py
```

### Expected Output:

```
Contract Configuration:
  Abstract contracts: ['VN30F1M', 'VN30F2M']
  Auto-detect enabled: True
  Custom mappings: {'VN30F1M': 'VN30F2511', 'VN30F2M': 'VN30F2512'}

Contract Resolution:
  Testing: VN30F1M
    Resolved to: VN30F2511
    ✅ Auto-detection successful
    Expiration: 2025-11-20
    Days to expiration: 7

  Testing: VN30F2M
    Resolved to: VN30F2512
    ✅ Auto-detection successful
    Expiration: 2025-12-18
    Days to expiration: 35

Redis Channels:
  Contract: VN30F1M → VN30F2511
    Channel: HNXDS:VN30F2511
```

## Common Issues and Solutions

### Issue 1: "Not receiving data from external feed"

**Problem:** Channel names don't match external feed

**Solution:**
1. Check what channels the external feed publishes to
2. Update `REDIS_CHANNEL_PREFIX` to match
3. Update `contract_mappings` to match their contract codes

**Example:** If external feed uses `FUTURES:VN30F2511`:
```bash
REDIS_CHANNEL_PREFIX=FUTURES
```

### Issue 2: "Wrong contract after rollover"

**Problem:** Contracts rolled over but mappings not updated

**Solution:** Update manual mappings monthly (third Thursday):

```json
{
  "contract_mappings": {
    "VN30F1M": "VN30F2512",  // Updated to December
    "VN30F2M": "VN30F2601"   // Updated to January
  }
}
```

### Issue 3: "Using wrong contracts"

**Problem:** `contracts` array has concrete codes but should have abstract symbols

**Solution:** When using mappings, the `contracts` array should list what you INPUT, not what you map TO:

```json
{
  "contracts": ["VN30F1M", "VN30F2M"],  // ✅ Correct - abstract symbols
  "contract_mappings": {
    "VN30F1M": "VN30F2511",
    "VN30F2M": "VN30F2512"
  }
}
```

NOT:
```json
{
  "contracts": ["VN30F2511", "VN30F2512"],  // ❌ Wrong - concrete codes
  "contract_mappings": {
    "VN30F1M": "VN30F2511",
    "VN30F2M": "VN30F2512"
  }
}
```

## Running Paper Trading

Once configured, run the paper trading engine:

```bash
# Using configuration from .env.redis
source .venv/bin/activate
python -m paper_trading.runner \
    --redis-env .env.redis \
    --mode live \
    --duration 300

# Expected channel subscriptions:
# ✅ Subscribed to: HNXDS:VN30F2511
# ✅ Subscribed to: HNXDS:VN30F2512
```

## Monthly Maintenance

### When to Update: Third Thursday of Each Month

**Example for December 2025 Rollover (Dec 18, 2025):**

**Before Rollover:**
```json
{
  "contract_mappings": {
    "VN30F1M": "VN30F2511",  // November (expires Dec 18)
    "VN30F2M": "VN30F2512"   // December
  }
}
```

**After Rollover:**
```json
{
  "contract_mappings": {
    "VN30F1M": "VN30F2512",  // December (new front month)
    "VN30F2M": "VN30F2601"   // January 2026
  }
}
```

## Summary

Your current setup is **working perfectly** ✅:

- ✅ Contract mappings apply correctly (VN30F1M → VN30F2511)
- ✅ Channel prefix configured (HNXDS)
- ✅ Redis authentication working
- ✅ External server mode detected
- ✅ All tests passing

**Next Steps:**
1. Monitor for live data during market hours (9:00 AM - 2:30 PM Vietnam time)
2. Update contract mappings before monthly rollover (third Thursday)
3. Run paper trading with `--mode live` to start live trading


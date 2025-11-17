# ProtoMarketMaker Configuration Guide

## Overview

ProtoMarketMaker uses a unified configuration approach with clear separation of concerns:
- **Redis settings** → Managed in one place
- **PaperBroker settings** → Only FIX/execution related settings
- **Strategy settings** → Trading parameters

## Configuration Files

### 1. Redis Configuration (Market Data)

**Location:** `.env.redis` (from `.env.redis.example`)
**Purpose:** ALL Redis settings for market data streaming

```bash
# Redis Connection Settings
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password_here  # Leave empty if no auth
REDIS_DECODE_RESPONSES=true
REDIS_CHANNEL_PREFIX=market
```

**Alternative:** `config/redis_config.json`
```json
{
  "redis_host": "localhost",
  "redis_port": 6379,
  "redis_db": 0,
  "redis_password": "",
  "redis_decode_responses": true,
  "channel_prefix": "market"
}
```

### 2. PaperBroker Configuration (Execution Only)

**Location:** `.env.paperbroker` (from `.env.paperbroker.example`)
**Purpose:** ONLY FIX protocol and execution settings

```bash
# FIX Connection Settings
PAPERBROKER_FIX_HOST=your.paperbroker.host
PAPERBROKER_FIX_PORT=5001
PAPERBROKER_SENDER_COMP_ID=PMM-TRADER-01
PAPERBROKER_TARGET_COMP_ID=SERVER
PAPERBROKER_FIX_USERNAME=your_username
PAPERBROKER_FIX_PASSWORD=your_password

# REST API Settings
PAPERBROKER_REST_BASE_URL=http://your.paperbroker.host:9090

# Trading Configuration
PAPERBROKER_SUB_ACCOUNT=D1
PAPERBROKER_CONTRACTS=VN30F2511,VN30F2512
```

**Note:** Redis settings are NOT duplicated here!

## Configuration Priority

Settings are loaded in this priority order (highest to lowest):

1. **Command-line arguments** - Override everything
2. **Environment files** (`.env.redis`, `.env.paperbroker`)
3. **JSON config files** (`config/*.json`)
4. **Default values** in code

## Usage Examples

### Mock Execution Mode (Default)

```bash
# Uses Redis for market data, mock execution
python -m paper_trading.runner \
    --redis-env .env.redis \
    --mode playback \
    --contracts VN30F1M
```

### PaperBroker Execution Mode

```bash
# Uses SAME Redis config, but real FIX execution
python -m paper_trading.runner \
    --redis-env .env.redis \
    --execution-mode paperbroker \
    --paperbroker-env .env.paperbroker \
    --mode live \
    --contracts VN30F2511
```

### Override Redis Settings via CLI

```bash
python -m paper_trading.runner \
    --redis-host prod.redis.server \
    --redis-port 6380 \
    --redis-password mysecret \
    --redis-db 1 \
    --mode live
```

## Common Configurations

### Local Development (No Auth)

**.env.redis:**
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_DECODE_RESPONSES=true
```

### Production (With Auth)

**.env.redis:**
```bash
REDIS_HOST=redis.prod.server.com
REDIS_PORT=6379
REDIS_DB=1
REDIS_PASSWORD=strong_password_here
REDIS_DECODE_RESPONSES=true
```

### Docker Redis

**.env.redis:**
```bash
REDIS_HOST=host.docker.internal  # On Mac/Windows
REDIS_HOST=172.17.0.1            # On Linux
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

## Important Notes

1. **Single Source of Truth**: Redis configuration is ONLY in `.env.redis` or `config/redis_config.json`
2. **No Duplication**: PaperBroker config does NOT contain Redis settings
3. **Both Modes Use Same Redis**: Mock and PaperBroker modes use the same Redis configuration
4. **Security**: Never commit actual `.env.*` files (only `.env.*.example` templates)

## Troubleshooting

### Redis Connection Failed

1. Check Redis is running:
```bash
redis-cli ping
```

2. Verify settings in `.env.redis`:
```bash
cat .env.redis | grep REDIS_
```

3. Test connection:
```python
import redis
r = redis.Redis(host='localhost', port=6379, password='', db=0)
r.ping()  # Should return True
```

### Wrong Configuration Loaded

Check priority order:
```bash
# See what's being used
python -m paper_trading.runner --log-level DEBUG 2>&1 | grep Redis
```

### PaperBroker Can't Find Redis

PaperBroker now uses the main Redis config. Ensure:
1. `.env.redis` exists and is configured
2. You're passing `--redis-env .env.redis` or it's in the default location

## Migration from Old Configuration

If you had Redis settings in `.env.paperbroker`:

1. Move Redis settings to `.env.redis`:
```bash
# Extract Redis settings from old file
grep "MARKET_REDIS" .env.paperbroker >> .env.redis
```

2. Remove Redis settings from `.env.paperbroker`:
```bash
# Remove old MARKET_REDIS_* lines
sed -i '/MARKET_REDIS/d' .env.paperbroker
```

3. Update your run scripts to use `--redis-env .env.redis`

## Summary

- **Redis config**: Use `.env.redis` for ALL Redis settings
- **PaperBroker config**: Use `.env.paperbroker` for FIX/execution ONLY
- **Both execution modes**: Use the same Redis configuration
- **No duplication**: Each setting appears in exactly one place
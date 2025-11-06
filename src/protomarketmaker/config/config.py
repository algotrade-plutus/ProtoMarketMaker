"""
Configuration module
"""

import os
import json
from dotenv import load_dotenv


load_dotenv()
host = os.getenv("HOST")
port = os.getenv("PORT")
database = os.getenv("DATABASE")
user = os.getenv("USER_DB")
password = os.getenv("PASSWORD")

db_params = {
    "host": host,
    "port": port,
    "database": database,
    "user": user,
    "password": password,
}

BACKTESTING_CONFIG = None
with open("parameter/backtesting_parameter.json", 'r', encoding="utf-8") as f:
    BACKTESTING_CONFIG = json.load(f)

OPTIMIZATION_CONFIG = None
with open("parameter/optimization_parameter.json", 'r', encoding="utf-8") as f:
    OPTIMIZATION_CONFIG = json.load(f)

BEST_CONFIG = None
with open("parameter/optimized_parameter.json", 'r', encoding="utf-8") as f:
    BEST_CONFIG = json.load(f)

# Load Redis configuration for paper trading
REDIS_CONFIG = None
redis_config_path = "config/redis_config.json"

if os.path.exists(redis_config_path):
    with open(redis_config_path, 'r', encoding="utf-8") as f:
        REDIS_CONFIG = json.load(f)
else:
    # Default configuration
    REDIS_CONFIG = {
        "redis_host": "localhost",
        "redis_port": 6379,
        "channel_prefix": "market",
        "contracts": ["VN30F1M"],
        "auto_detect_contracts": True,
        "contract_mappings": {},
        "confirm_symbols": True,
        "initial_capital": 500000,
        "step": 2.9,
        "update_interval_seconds": 15,
        "record_events": False,
        "event_log_path": "logs/paper_trading/events.jsonl"
    }

# Environment variable overrides for Redis config
if 'REDIS_HOST' in os.environ:
    REDIS_CONFIG['redis_host'] = os.environ['REDIS_HOST']
if 'REDIS_PORT' in os.environ:
    REDIS_CONFIG['redis_port'] = int(os.environ['REDIS_PORT'])

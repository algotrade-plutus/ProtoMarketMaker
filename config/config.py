"""
Configuration module
"""

import os
import json
from dotenv import load_dotenv


load_dotenv()
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
database = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

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

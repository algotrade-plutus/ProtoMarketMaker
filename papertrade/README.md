
---

## Running the Market Maker Paper Trading

```bash
python3 papertrade/paper.py
```

Console output shows the latest matched price, placed orders, balances, and portfolio state in real time.

---

## ⚙️ Environment Setup

All required credentials and configurations are stored in a `.env` file.
Create a `.env` in the project root:

```ini
# Paper Broker account credentials
PAPER_ACCOUNT=
PAPER_USERNAME=
PAPER_PASSWORD=
PAPER_CFG=
PAPER_REST_BASE_URL=

# Kafka connection settings
KAFKA_BOOTSTRAP_SERVERS=
KAFKA_TOPIC=
INSTRUMENT=
KAFKA_USERNAME=
KAFKA_PASSWORD=
```

Then install dependencies and run the strategy:

```bash
pip install -r requirements.txt
python3 papertrade/paper.py
```

---

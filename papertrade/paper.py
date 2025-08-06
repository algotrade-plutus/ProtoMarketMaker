import os
import time
import json
from datetime import datetime
from dotenv import load_dotenv
from paperbroker import PaperBrokerClient
from kafka import KafkaConsumer

# Load environment variables from .env
load_dotenv()

client = PaperBrokerClient(
    account=os.getenv("PAPER_ACCOUNT"),
    username=os.getenv("PAPER_USERNAME"),
    password=os.getenv("PAPER_PASSWORD"),
    cfg_path=os.getenv("PAPER_CFG"),
    console=False,
    rest_base_url=os.getenv("PAPER_REST_BASE_URL"),
)

# Kafka configs (use your own values in .env or config file)
KAFKA_BOOTSTRAP_SERVERS = [os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")]
TOPIC_NAME = os.getenv("KAFKA_TOPIC", "example.topic")
GROUP_ID = f"example-{int(time.time())}"
INSTRUMENT = os.getenv("INSTRUMENT", "EXCHANGE:SYMBOL")

print(f"Connecting to Kafka topic '{TOPIC_NAME}' with group ID '{GROUP_ID}'...")
print(f"Using instrument: {INSTRUMENT}")

kafka = KafkaConsumer(
    TOPIC_NAME,
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    security_protocol="SASL_PLAINTEXT",
    sasl_mechanism="PLAIN",
    sasl_plain_username=os.getenv("KAFKA_USERNAME", "your-username"),
    sasl_plain_password=os.getenv("KAFKA_PASSWORD", "your-password"),
    group_id=GROUP_ID,
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    auto_offset_reset="latest",
    enable_auto_commit=True,
)

# === Trading state ===
inventory, bid, ask, price = 0, None, None, None
step = 2.9
bid_cl_ord_id = ask_cl_ord_id = None
latest_place_time = None


def get_latest_matched_price(timeout=1):
    msg_pack = kafka.poll(timeout_ms=timeout * 1000, max_records=10)
    for messages in msg_pack.values():
        for msg in reversed(messages):
            return (
                msg.value.get("quote_entries", {})
                .get("latest_matched_price", {})
                .get("value")
            )
    return None


def place_order():
    global bid_cl_ord_id, ask_cl_ord_id, latest_place_time

    # Cancel old orders
    for cl_id in (bid_cl_ord_id, ask_cl_ord_id):
        if cl_id:
            client.cancel_order(cl_id)

    # Place new orders
    bid_cl_ord_id = client.place_order(INSTRUMENT, "BUY", 1, bid)
    ask_cl_ord_id = client.place_order(INSTRUMENT, "SELL", 1, ask)
    latest_place_time = time.time()


def update_inventory(portfolio):
    global inventory, bid, ask

    new_quantity = next(
        (
            h.get("quantity", 0)
            for h in portfolio.get("holdings", [])
            if h.get("instrument") == INSTRUMENT
        ),
        0,
    )
    if new_quantity < inventory:
        ask = None
    elif new_quantity > inventory:
        bid = None
    inventory = new_quantity


try:
    client.connect()

    while True:
        now = datetime.now()
        if now.hour >= 15:
            print(f"[{now:%H:%M:%S}] Market closed. Exiting...")
            break

        price = get_latest_matched_price() or price
        if price is None:
            print(f"[{now:%H:%M:%S}] No price data. Retrying...")
            time.sleep(1)
            continue
        print(f"[{now:%H:%M:%S}] Latest matched price: {price}")

        if bid is None or ask is None:
            bid = round((price - step) - step * max(inventory, 0) * 0.02, 1)
            ask = round((price + step) + step * min(inventory, 0) * 0.02, 1)

        update_inventory(client.get_portfolio())

        if (
            bid_cl_ord_id is None
            or ask_cl_ord_id is None
            or (latest_place_time and time.time() - latest_place_time > 15)
        ):
            bid = round((price - step) - step * max(inventory, 0) * 0.02, 1)
            ask = round((price + step) + step * min(inventory, 0) * 0.02, 1)
            place_order()
            print(f"[{now:%H:%M:%S}] Placed: bid={bid}, ask={ask}, inv={inventory}")
            print(
                f"[{now:%H:%M:%S}] Total balance: {client.get_total_balance()} "
                f"Latest matched price: {price}"
            )
            print(f"[{now:%H:%M:%S}] Portfolio: {client.get_portfolio()}")

finally:
    client.disconnect()

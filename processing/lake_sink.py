"""Kafka -> data lake (raw zone), one JSON-lines file per topic every 60 s.

Offsets are committed only AFTER the file is written, so a crash never loses data
(at worst a minute is written twice; later steps de-duplicate).
Stores candles and news. Raw trades are not stored: candles already carry the
trade count and taker-buy volume, which is all the features need.
"""
import logging
import time
from datetime import datetime, timezone

from common.config import KAFKA, TOPIC_KLINES, TOPIC_NEWS
from common.storage import put_bytes

log = logging.getLogger("lake-sink")
TOPICS = [TOPIC_KLINES, TOPIC_NEWS]


def raw_key(topic: str, now: datetime) -> str:
    return f"raw/{topic}/dt={now:%Y-%m-%d}/hour={now:%H}/{int(now.timestamp())}.json"


def run(flush_every_s=60):
    from confluent_kafka import Consumer, KafkaException

    consumer = Consumer({"bootstrap.servers": KAFKA, "group.id": "lake-sink",
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    consumer.subscribe(TOPICS)
    buffers = {t: [] for t in TOPICS}
    last = time.time()
    while True:
        msg = consumer.poll(1.0)
        if msg is not None and not msg.error():
            buffers[msg.topic()].append(msg.value().decode())
        if time.time() - last >= flush_every_s:
            now = datetime.now(timezone.utc)
            for topic, rows in buffers.items():
                if rows:
                    where = put_bytes(raw_key(topic, now), "\n".join(rows).encode())
                    log.info("wrote %d rows -> %s", len(rows), where)
                    rows.clear()
            try:
                consumer.commit(asynchronous=False)
            except KafkaException:
                pass  # nothing new to commit
            last = time.time()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run()

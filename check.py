import os
import sqlite3
import sys

from confluent_kafka import Consumer, TopicPartition
from dotenv import load_dotenv

TOPIC = "mblife.pbx.cdr.v1"
DB_PATH = "cdr.db"
CHECK_GROUP_ID = "cdr-check-readonly"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv()
    vm_ip = os.getenv("VM_IP", "").strip().strip("'")
    if not vm_ip:
        print("Thiếu VM_IP trong .env")
        sys.exit(1)

    consumer = Consumer(
        {
            "bootstrap.servers": f"{vm_ip}:9092",
            "group.id": CHECK_GROUP_ID,
            "enable.auto.commit": False,
        }
    )

    try:
        meta = consumer.list_topics(TOPIC, timeout=15)
        if TOPIC not in meta.topics:
            print(f"Không tìm thấy topic {TOPIC}")
            sys.exit(1)

        partition_ids = sorted(meta.topics[TOPIC].partitions.keys())
        rows: list[tuple[int, int]] = []
        kafka_total = 0

        for pid in partition_ids:
            tp = TopicPartition(TOPIC, pid)
            _low, high = consumer.get_watermark_offsets(tp, timeout=15)
            rows.append((pid, high))
            kafka_total += high

        print(f"{'partition':>10}  {'high':>10}")
        print(f"{'-' * 10}  {'-' * 10}")
        for pid, high in rows:
            print(f"{pid:>10}  {high:>10}")
        print(f"{'TỔNG':>10}  {kafka_total:>10}")

        if not os.path.isfile(DB_PATH):
            print(f"Không tìm thấy {DB_PATH}")
            sys.exit(1)

        conn = sqlite3.connect(DB_PATH)
        db_total = conn.execute("SELECT COUNT(*) FROM cdr").fetchone()[0]
        conn.close()
        print(f"\nSố dòng trong cdr.db: {db_total}")

        if kafka_total == db_total:
            print("OK")
        else:
            print(f"LỆCH {abs(kafka_total - db_total)}")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()

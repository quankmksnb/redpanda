import json
import os
import signal
import socket
import sqlite3
import sys

from confluent_kafka import Consumer, KafkaError, KafkaException
from dotenv import load_dotenv

TOPIC = "mblife.pbx.cdr.v1"
GROUP_ID = "cdr-backend-writer"
DB_PATH = "cdr.db"

UPSERT_SQL = """
INSERT INTO cdr (
    linkedid, src, dst, "start", "end", billsec, disposition,
    kafka_partition, kafka_offset
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(linkedid) DO UPDATE SET
    src = excluded.src,
    dst = excluded.dst,
    "start" = excluded."start",
    "end" = excluded."end",
    billsec = excluded.billsec,
    disposition = excluded.disposition,
    kafka_partition = excluded.kafka_partition,
    kafka_offset = excluded.kafka_offset
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cdr (
            linkedid TEXT PRIMARY KEY,
            src TEXT,
            dst TEXT,
            "start" TEXT,
            "end" TEXT,
            billsec INTEGER,
            disposition TEXT,
            kafka_partition INTEGER,
            kafka_offset INTEGER
        )
        """
    )
    conn.commit()


def on_assign(consumer: Consumer, partitions) -> None:
    worker = f"{socket.gethostname()}-{os.getpid()}"
    names = ", ".join(f"{p.topic}[{p.partition}]" for p in partitions)
    print(f"[{worker}] partition được giao: {names}")


def parse_row(msg) -> tuple | None:
    raw = msg.value()
    if raw is None:
        print(
            f"Cảnh báo: message null tại partition={msg.partition()} "
            f"offset={msg.offset()}, bỏ qua."
        )
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(
            f"Cảnh báo: JSON hỏng tại partition={msg.partition()} "
            f"offset={msg.offset()} ({exc}), bỏ qua."
        )
        return None

    linkedid = data.get("linkedid")
    if not linkedid:
        print(
            f"Cảnh báo: thiếu linkedid tại partition={msg.partition()} "
            f"offset={msg.offset()}, bỏ qua."
        )
        return None

    return (
        linkedid,
        data.get("src"),
        data.get("dst"),
        data.get("start"),
        data.get("end"),
        data.get("billsec"),
        data.get("disposition"),
        msg.partition(),
        msg.offset(),
    )


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
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC], on_assign=on_assign)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    processed = 0
    running = True

    def stop(_signum=None, _frame=None) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    try:
        while running:
            msgs = consumer.consume(num_messages=100, timeout=1.0)
            if not msgs:
                continue

            batch_ok = False
            conn.execute("BEGIN")
            try:
                for msg in msgs:
                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        raise KafkaException(msg.error())

                    row = parse_row(msg)
                    if row is None:
                        processed += 1
                        continue

                    conn.execute(UPSERT_SQL, row)
                    processed += 1

                conn.commit()
                batch_ok = True
            except Exception:
                conn.rollback()
                raise

            if batch_ok:
                consumer.commit(asynchronous=False)
    except KeyboardInterrupt:
        stop()
    finally:
        consumer.close()
        total = conn.execute("SELECT COUNT(*) FROM cdr").fetchone()[0]
        conn.close()
        print(f"Đã xử lý lần chạy này: {processed} message.")
        print(f"Tổng dòng trong bảng cdr: {total}.")


if __name__ == "__main__":
    main()

import argparse
import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from confluent_kafka import Producer
from dotenv import load_dotenv

TOPIC = "mblife.pbx.cdr.v1"
TZ = timezone(timedelta(hours=7))


def iso_local(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def build_cdr(linkedid: str) -> dict:
    billsec = random.randint(0, 600)
    direction = random.choice(("inbound", "outbound"))
    src = "09" + "".join(str(random.randint(0, 9)) for _ in range(8))
    start = datetime.now(TZ)
    ring = random.randint(3, 20)

    if billsec == 0:
        answer = None
        disposition = "NO ANSWER"
        duration = ring
        end = start + timedelta(seconds=duration)
    else:
        answer = start + timedelta(seconds=ring)
        disposition = "ANSWERED"
        duration = ring + billsec
        end = answer + timedelta(seconds=billsec)

    return {
        "linkedid": linkedid,
        "uniqueid": f"{linkedid}.{random.randint(1000, 9999)}",
        "direction": direction,
        "src": src,
        "dst": "1001",
        "start": iso_local(start),
        "answer": iso_local(answer) if answer else None,
        "end": iso_local(end),
        "duration": duration,
        "billsec": billsec,
        "disposition": disposition,
        "recording_url": None,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Gửi CDR giả vào Redpanda")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()
    if args.count < 1:
        print("--count phải >= 1")
        sys.exit(1)

    load_dotenv()
    vm_ip = os.getenv("VM_IP", "").strip().strip("'")
    if not vm_ip:
        print("Thiếu VM_IP trong .env")
        sys.exit(1)

    run_id = time.time_ns()
    producer = Producer(
        {
            "bootstrap.servers": f"{vm_ip}:9092",
            "acks": "all",
            "enable.idempotence": True,
            "compression.type": "zstd",
        }
    )

    stats = {"ok": 0, "fail": 0}
    lock = threading.Lock()
    pending = args.count

    def on_delivery(err, msg) -> None:
        nonlocal pending
        with lock:
            if err is not None:
                stats["fail"] += 1
                print(f"Lỗi gửi: {err}")
            else:
                stats["ok"] += 1
                if args.count <= 10:
                    print(
                        f"linkedid={msg.key().decode()} "
                        f"partition={msg.partition()} offset={msg.offset()}"
                    )
            pending -= 1

    for i in range(1, args.count + 1):
        linkedid = f"{run_id}.{i}"
        payload = build_cdr(linkedid)
        producer.produce(
            TOPIC,
            key=linkedid.encode("utf-8"),
            value=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            callback=on_delivery,
        )

    producer.flush()

    with lock:
        if pending != 0:
            print(f"Cảnh báo: còn {pending} callback chưa chạy sau flush.")

    print(f"Thành công: {stats['ok']}, thất bại: {stats['fail']}")
    if stats["fail"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

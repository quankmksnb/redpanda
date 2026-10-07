import os
import sys

from dotenv import load_dotenv

REQUIRED = ("VULTR_API_KEY", "LAB_NAME")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv()
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        for name in missing:
            print(f"Thiếu biến: {name}")
        sys.exit(1)

    lab_name = os.environ["LAB_NAME"].strip()
    key = os.environ["VULTR_API_KEY"].strip()
    vm_ip = os.getenv("VM_IP", "").strip()
    print(f"LAB_NAME={lab_name}")
    print(f"VULTR_API_KEY=...{key[-4:]}")
    if vm_ip:
        print(f"VM_IP={vm_ip}")
    else:
        print("VM_IP: chưa có (sẽ được ghi ở bài 2b)")


if __name__ == "__main__":
    main()

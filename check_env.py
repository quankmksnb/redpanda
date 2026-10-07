import os
import sys

from dotenv import load_dotenv

REQUIRED = ("VULTR_API_KEY", "LAB_NAME", "VM_IP")


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
    print(f"LAB_NAME={lab_name}")
    print(f"VULTR_API_KEY=...{key[-4:]}")


if __name__ == "__main__":
    main()

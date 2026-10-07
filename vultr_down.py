import argparse
import os
import sys
import time

from dotenv import load_dotenv

from vultr_up import call, call_paginated


def find_lab_instance(lab_name: str) -> dict | None:
    instances = call_paginated("/instances", "instances")
    return next((i for i in instances if i.get("label") == lab_name), None)


def find_lab_firewall(lab_name: str) -> dict | None:
    groups = call_paginated("/firewalls", "firewall_groups")
    return next((g for g in groups if g.get("description") == lab_name), None)


def find_lab_ssh_key(lab_name: str) -> dict | None:
    keys = call_paginated("/ssh-keys", "ssh_keys")
    return next((k for k in keys if k.get("name") == lab_name), None)


def wait_instance_gone(lab_name: str) -> None:
    while find_lab_instance(lab_name) is not None:
        print("Chờ instance biến mất khỏi danh sách...")
        time.sleep(10)


def confirm_delete(lab_name: str, skip: bool) -> None:
    if skip:
        return
    typed = input(f"Gõ lại LAB_NAME ({lab_name}) để xác nhận xoá: ").strip()
    if typed != lab_name:
        print("LAB_NAME không khớp — huỷ, không xoá gì.")
        sys.exit(1)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Dọn tài nguyên Vultr của lab (theo LAB_NAME)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Bỏ qua bước gõ lại LAB_NAME để xác nhận",
    )
    args = parser.parse_args()

    load_dotenv()
    lab_name = os.getenv("LAB_NAME", "").strip()
    if not lab_name:
        print("Thiếu biến: LAB_NAME")
        sys.exit(1)
    if not os.getenv("VULTR_API_KEY", "").strip():
        print("Thiếu biến: VULTR_API_KEY")
        sys.exit(1)

    instance = find_lab_instance(lab_name)
    firewall = find_lab_firewall(lab_name)
    ssh_key = find_lab_ssh_key(lab_name)

    if not instance and not firewall and not ssh_key:
        print("Không còn tài nguyên nào.")
        return

    print(f"=== vultr_down (LAB_NAME={lab_name}) ===\n")
    print("Sẽ xoá (chỉ tài nguyên khớp LAB_NAME):")
    if instance:
        print(f"  - instance  label={lab_name!r}  id={instance['id']}")
    if firewall:
        print(f"  - firewall  description={lab_name!r}  id={firewall['id']}")
    if ssh_key:
        print(f"  - ssh key   name={lab_name!r}  id={ssh_key['id']}")
    print()

    confirm_delete(lab_name, args.yes)

    if instance:
        iid = instance["id"]
        print(f"Đang xoá instance {iid}...")
        call("DELETE", f"/instances/{iid}")
        wait_instance_gone(lab_name)
        print("Instance đã biến mất.")

    if firewall:
        fid = firewall["id"]
        print(f"Đang xoá firewall group {fid}...")
        call("DELETE", f"/firewalls/{fid}")
        print("Đã xoá firewall group.")

    if ssh_key:
        kid = ssh_key["id"]
        print(f"Đang xoá SSH key {kid}...")
        call("DELETE", f"/ssh-keys/{kid}")
        print("Đã xoá SSH key.")

    print("Hoàn tất dọn lab.")


if __name__ == "__main__":
    main()

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

BASE_URL = "https://api.vultr.com/v2"
OS_ID_UBUNTU_2404 = 2284
REGION = "sgp"
PLAN = "vc2-2c-4gb"
ENV_PATH = Path(".env")


def call(
    method: str,
    path: str,
    params: dict | None = None,
    json_body: dict | None = None,
) -> dict:
    api_key = os.environ["VULTR_API_KEY"].strip()
    url = f"{BASE_URL}{path}"
    resp = requests.request(
        method,
        url,
        params=params,
        json=json_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=120,
    )
    if not resp.ok:
        print(f"Lỗi HTTP {resp.status_code} khi {method} {path}")
        print(resp.text)
        sys.exit(1)
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()


def call_paginated(path: str, list_key: str, params: dict | None = None) -> list:
    items: list = []
    cursor: str | None = None
    base_params = dict(params or {})

    while True:
        page_params = dict(base_params)
        if cursor:
            page_params["cursor"] = cursor
        data = call("GET", path, params=page_params)
        items.extend(data.get(list_key, []))
        meta = data.get("meta") or {}
        links = (meta.get("links") or {})
        cursor = links.get("next")
        if not cursor:
            break
    return items


def get_public_ip() -> str:
    resp = requests.get("https://api.ipify.org", timeout=30)
    resp.raise_for_status()
    ip = resp.text.strip()
    if not ip or "/" in ip:
        print(f"IP public không hợp lệ: {ip!r}")
        sys.exit(1)
    return ip


def ensure_ssh_key(lab_name: str) -> str:
    keys = call_paginated("/ssh-keys", "ssh_keys")
    existing = next((k for k in keys if k.get("name") == lab_name), None)
    if existing:
        key_id = existing["id"]
        print(f"SSH key '{lab_name}' đã có (id={key_id}).")
        return key_id

    pub_path = Path("~/.ssh/id_ed25519.pub").expanduser()
    if not pub_path.is_file():
        print(f"Không tìm thấy public key: {pub_path}")
        sys.exit(1)
    ssh_key = pub_path.read_text(encoding="utf-8").strip()
    data = call(
        "POST",
        "/ssh-keys",
        json_body={"name": lab_name, "ssh_key": ssh_key},
    )
    key_id = data["ssh_key"]["id"]
    print(f"Đã tạo SSH key '{lab_name}' (id={key_id}).")
    return key_id


def ensure_firewall_group(lab_name: str) -> str:
    groups = call_paginated("/firewalls", "firewall_groups")
    existing = next((g for g in groups if g.get("description") == lab_name), None)
    if existing:
        group_id = existing["id"]
        print(f"Firewall group '{lab_name}' đã có (id={group_id}).")
        return group_id

    data = call("POST", "/firewalls", json_body={"description": lab_name})
    group_id = data["firewall_group"]["id"]
    print(f"Đã tạo firewall group '{lab_name}' (id={group_id}).")
    return group_id


def rule_matches(rule: dict, port: str, my_ip: str) -> bool:
    if rule.get("protocol") != "tcp":
        return False
    if str(rule.get("port", "")) != port:
        return False
    if rule.get("subnet") != my_ip:
        return False
    if int(rule.get("subnet_size", -1)) != 32:
        return False
    if rule.get("ip_type") != "v4":
        return False
    return True


def ensure_firewall_rules(group_id: str, my_ip: str) -> None:
    rules = call_paginated(f"/firewalls/{group_id}/rules", "firewall_rules")
    for port in ("22", "9092"):
        if any(rule_matches(r, port, my_ip) for r in rules):
            print(
                f"Rule TCP {port} từ {my_ip}/32 đã có trong firewall group {group_id}."
            )
            continue
        call(
            "POST",
            f"/firewalls/{group_id}/rules",
            json_body={
                "ip_type": "v4",
                "protocol": "tcp",
                "port": port,
                "subnet": my_ip,
                "subnet_size": 32,
                "notes": f"lab inbound tcp/{port}",
            },
        )
        print(f"Đã thêm rule TCP {port} từ {my_ip}/32.")


def find_instance_by_label(lab_name: str) -> dict | None:
    instances = call_paginated("/instances", "instances")
    return next((i for i in instances if i.get("label") == lab_name), None)


def ensure_instance(
    lab_name: str,
    ssh_key_id: str,
    firewall_group_id: str,
) -> str:
    existing = find_instance_by_label(lab_name)
    if existing:
        instance_id = existing["id"]
        print(f"Instance label '{lab_name}' đã có (id={instance_id}).")
        return instance_id

    data = call(
        "POST",
        "/instances",
        json_body={
            "region": REGION,
            "plan": PLAN,
            "os_id": OS_ID_UBUNTU_2404,
            "label": lab_name,
            "sshkey_id": [ssh_key_id],
            "firewall_group_id": firewall_group_id,
            "tags": ["lab"],
            "backups": "disabled",
        },
    )
    instance_id = data["instance"]["id"]
    print(f"Đã tạo instance '{lab_name}' (id={instance_id}).")
    return instance_id


def wait_until_ready(instance_id: str) -> dict:
    while True:
        data = call("GET", f"/instances/{instance_id}")
        inst = data["instance"]
        status = inst.get("status")
        power = inst.get("power_status")
        server = inst.get("server_status")
        print(f"  status={status}, power_status={power}, server_status={server}")
        if status == "active" and power == "running" and server == "ok":
            return inst
        time.sleep(10)


def write_vm_ip(main_ip: str) -> None:
    env_file = str(ENV_PATH)
    if not ENV_PATH.is_file():
        print(f"Không tìm thấy {ENV_PATH}")
        sys.exit(1)
    set_key(env_file, "VM_IP", main_ip)
    print(f"Đã ghi VM_IP={main_ip} vào .env")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv()
    lab_name = os.getenv("LAB_NAME", "").strip()
    if not lab_name:
        print("Thiếu biến: LAB_NAME")
        sys.exit(1)
    if not os.getenv("VULTR_API_KEY", "").strip():
        print("Thiếu biến: VULTR_API_KEY")
        sys.exit(1)

    print(f"=== vultr_up (LAB_NAME={lab_name}) ===\n")

    my_ip = get_public_ip()
    print(f"IP public của tôi: {my_ip}/32\n")

    print("--- SSH key ---")
    ssh_key_id = ensure_ssh_key(lab_name)

    print("\n--- Firewall ---")
    firewall_id = ensure_firewall_group(lab_name)
    ensure_firewall_rules(firewall_id, my_ip)

    print("\n--- Instance ---")
    instance_id = ensure_instance(lab_name, ssh_key_id, firewall_id)

    print("\n--- Chờ instance sẵn sàng ---")
    inst = wait_until_ready(instance_id)
    main_ip = inst.get("main_ip", "").strip()
    if not main_ip:
        print("Instance active nhưng không có main_ip.")
        sys.exit(1)

    write_vm_ip(main_ip)
    print("\nHoàn tất.")


if __name__ == "__main__":
    main()

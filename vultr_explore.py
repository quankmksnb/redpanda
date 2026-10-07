import os
import sys

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.vultr.com/v2"


def call(path: str, params: dict | None = None) -> dict:
    api_key = os.environ["VULTR_API_KEY"].strip()
    url = f"{BASE_URL}{path}"
    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if not resp.ok:
        print(f"Lỗi HTTP {resp.status_code} khi GET {path}")
        print(resp.text)
        sys.exit(1)
    return resp.json()


def call_paginated(path: str, params: dict | None = None, list_key: str = "") -> list:
    items: list = []
    cursor: str | None = None
    base_params = dict(params or {})

    while True:
        page_params = dict(base_params)
        if cursor:
            page_params["cursor"] = cursor
        data = call(path, page_params)
        items.extend(data.get(list_key, []))
        meta = data.get("meta") or {}
        links = meta.get("links") or {}
        cursor = links.get("next")
        if not cursor:
            break
    return items


def format_balance(balance: float) -> str:
    if balance < 0:
        credit = -balance
        return f"credit còn lại: ${credit:.2f} (balance API = {balance:.2f})"
    if balance > 0:
        return f"nợ tài khoản: ${balance:.2f} (balance API = {balance:.2f})"
    return "số dư = 0"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv()
    if not os.getenv("VULTR_API_KEY", "").strip():
        print("Thiếu biến: VULTR_API_KEY")
        sys.exit(1)

    print("=== Tài khoản ===")
    account = call("/account")["account"]
    balance = float(account["balance"])
    pending = float(account.get("pending_charges", 0))
    print(format_balance(balance))
    print(f"phí đang chờ tính: ${pending:.2f}")

    print("\n=== Region sgp ===")
    regions = call_paginated("/regions", list_key="regions")
    sgp = next((r for r in regions if r.get("id") == "sgp"), None)
    if sgp:
        city = sgp.get("city", "")
        country = sgp.get("country", "")
        print(f'Có region "sgp" ({city}, {country}).')
    else:
        print('Không tìm thấy region "sgp".')
        sys.exit(1)

    print("\n=== Plan vc2-2c-4gb ===")
    plans = call_paginated("/plans", params={"type": "vc2"}, list_key="plans")
    plan = next((p for p in plans if p.get("id") == "vc2-2c-4gb"), None)
    if not plan:
        print('Không tìm thấy plan "vc2-2c-4gb".')
        sys.exit(1)
    ram_mb = int(plan["ram"])
    ram_gb = ram_mb / 1024
    monthly = float(plan["monthly_cost"])
    locations = plan.get("locations") or []
    in_sgp = "sgp" in locations
    print(f"vCPU: {plan['vcpu_count']}")
    print(f"RAM: {ram_mb} MB ({ram_gb:g} GB)")
    print(f"Giá tháng: ${monthly:.2f}")
    print(f"Có ở sgp: {'có' if in_sgp else 'không'}")

    print("\n=== OS Ubuntu 24.04 LTS x64 ===")
    os_list = call_paginated("/os", list_key="os")
    target_name = "Ubuntu 24.04 LTS x64"
    ubuntu = next((o for o in os_list if o.get("name") == target_name), None)
    if not ubuntu:
        print(f'Không tìm thấy OS "{target_name}".')
        sys.exit(1)
    print(f"os_id = {ubuntu['id']} ({ubuntu['name']})")


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
set -euo pipefail

VM_IP="${1:?Cách dùng: $0 <VM_IP>}"

if ! command -v rpk >/dev/null 2>&1; then
  echo "Chưa có rpk — thêm repo apt và cài redpanda..."
  curl -1sLf "https://linux.pkg.redpanda.com/setup-redpanda.deb.sh" | bash
  apt-get update -qq
  apt-get install -y redpanda
else
  echo "rpk đã có, bỏ qua cài apt."
fi

echo "Cấu hình bootstrap một node (IP=${VM_IP})..."
rpk redpanda config bootstrap \
  --self "$VM_IP" \
  --advertised-kafka "$VM_IP" \
  --ips "$VM_IP"

rpk redpanda config set redpanda.empty_seed_starts_cluster false
rpk redpanda config set rpk.additional_start_flags '["--memory=2G"]'

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  if ! ufw status | grep -qE "^9092/tcp"; then
    echo "UFW đang bật — cho phép TCP 9092 (Vultr firewall đã giới hạn nguồn)."
    ufw allow 9092/tcp comment "redpanda kafka"
  else
    echo "UFW: rule 9092/tcp đã có."
  fi
fi

echo "Bật và khởi động lại service redpanda..."
systemctl enable redpanda
systemctl restart redpanda

echo "Chờ cluster healthy (tối đa 60 giây)..."
deadline=$((SECONDS + 60))
healthy=false
while (( SECONDS < deadline )); do
  if rpk cluster health 2>/dev/null | grep -qE "Healthy:[[:space:]]+true"; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "$healthy" != true ]]; then
  echo "Cluster chưa healthy sau 60 giây." >&2
  rpk cluster health || true
  exit 1
fi

echo "=== rpk cluster info ==="
rpk cluster info

echo "Hoàn tất — Redpanda healthy."

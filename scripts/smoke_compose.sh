#!/usr/bin/env bash
# Kiểm tra `docker compose up` end-to-end: dựng, đợi API + MCP sẵn sàng, gọi thử rồi dọn.
#   scripts/smoke_compose.sh            # dọn sau khi xong (docker compose down -v)
#   KEEP=1 scripts/smoke_compose.sh     # giữ container chạy để thử tiếp
set -euo pipefail
cd "$(dirname "$0")/.."

cleanup() { [ "${KEEP:-0}" = "1" ] || docker compose down -v >/dev/null 2>&1; }
trap cleanup EXIT

docker compose up -d --build

echo "Đợi API (http://127.0.0.1:8000/health)..."
for _ in $(seq 1 90); do
  curl -sf http://127.0.0.1:8000/health >/dev/null && break
  sleep 2
done
curl -sf http://127.0.0.1:8000/health
echo

echo "Đợi MCP (http://127.0.0.1:8002/mcp)..."
for _ in $(seq 1 30); do
  python3 scripts/smoke_mcp.py http://127.0.0.1:8002/mcp && exit 0
  sleep 2
done
echo "MCP không sẵn sàng" >&2
docker compose logs --tail 40 >&2
exit 1

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f .env ]] || cp .env.example .env

API_PORT="$(grep -E '^API_PORT=' .env | tail -1 | cut -d= -f2 || true)"
API_PORT="${API_PORT:-8000}"
BASE_URL="http://localhost:${API_PORT}"

docker info >/dev/null
docker compose config >/dev/null
docker compose --profile tools run --rm etl python -m src.cli validate-sources >/dev/null
docker compose --profile tools run --rm etl pytest -q
docker compose exec -T api python -m src.cli validate >/dev/null

python - "$BASE_URL" <<'PY'
import json, sys, urllib.request
base = sys.argv[1]
def get(path):
    return json.load(urllib.request.urlopen(base + path, timeout=20))
assert get("/health")["status"] == "ok"
assert get("/health")["version"] == "2.5.1"
stats = get("/stats")
assert stats["total_count"] == 145393
voo = get("/products/PREF02N001/589")
assert voo["product_id"] == "VOO"
assert voo["price_base_date"] == "2026-06-16"
assert voo["size_base_date"] == "2026-06-14"
result = get("/products/search?product_type=OVERSEAS_ETF&sort_by=size&order=desc&limit=3")
assert result["returned_count"] == 3
assert len(result["items"]) == 3
print("Base API checks passed.")
PY

python scripts/phase2_smoke_test.py "$BASE_URL"
python scripts/phase25_smoke_test.py "$BASE_URL"

echo "전체 검증 결과: 모두 정상"
echo "1·2차와 온톨로지·지식그래프·Federated 검색·Answer Validation까지 통과했습니다."

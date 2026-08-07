#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f .env ]] || cp .env.example .env

command -v docker >/dev/null 2>&1 || {
  echo "Docker is not installed." >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "Docker Engine is not running." >&2
  exit 1
}

echo "[1/7] Validate Docker Compose"
docker compose config >/dev/null

echo "[2/7] Build API and ETL images"
docker compose --profile tools build api etl

echo "[3/7] Start PostgreSQL"
docker compose stop api >/dev/null 2>&1 || true
docker compose up -d postgres

echo "[4/7] Validate, preprocess, load, index, and build knowledge graph"
docker compose --profile tools run --rm etl

echo "[5/7] Restore optional historical external evidence"
if [[ -f external_data/holdings.jsonl ]]; then
  docker compose --profile tools run --rm etl python -m src.semantic.ingest_holdings /app/external_data/holdings.jsonl
fi
if [[ -f external_data/documents.jsonl ]]; then
  docker compose --profile tools run --rm etl python -m src.semantic.ingest /app/external_data/documents.jsonl
fi

echo "[6/7] Start API"
docker compose up -d --force-recreate api

API_PORT="$(grep -E '^API_PORT=' .env | tail -1 | cut -d= -f2 || true)"
API_PORT="${API_PORT:-8000}"
ready=0
for _ in $(seq 1 45); do
  if python - "$API_PORT" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
try:
    payload = json.load(urllib.request.urlopen(f"http://localhost:{port}/health", timeout=3))
    raise SystemExit(0 if payload.get("status") == "ok" else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" != "1" ]]; then
  docker compose logs --tail 100 api
  echo "API did not become ready in time." >&2
  exit 1
fi

echo "[7/7] Run full validation"
bash scripts/check-all.sh

echo "Done: http://localhost:${API_PORT}/docs"

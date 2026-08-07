.PHONY: bootstrap check reset sources profile test smoke phase2-smoke down logs

bootstrap:
	powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1"

check:
	powershell -ExecutionPolicy Bypass -File ".\scripts\check-all.ps1"

reset:
	powershell -ExecutionPolicy Bypass -File ".\scripts\reset-and-run.ps1"

sources:
	docker compose --profile tools run --rm etl python -m src.cli validate-sources

profile:
	docker compose --profile tools run --rm etl python -m src.cli preprocess

test:
	docker compose --profile tools run --rm etl pytest -q

smoke:
	docker compose --profile tools run --rm etl python -m src.cli preprocess --max-rows 100

phase2-smoke:
	python scripts/phase2_smoke_test.py http://localhost:8000

down:
	docker compose down

logs:
	docker compose logs --tail 200 api postgres

.PHONY: dev-env up down logs status config build migrate seed baseline test lint helm-lint

dev-env:
	./scripts/dev.sh env

up:
	./scripts/dev.sh up

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm --no-deps -v "$(PWD)/docs:/app/docs:ro" -v "$(PWD)/scripts:/app/scripts:ro" api python /app/scripts/seed_case.py

baseline:
	docker compose run --rm --no-deps -v "$(PWD)/scripts:/app/scripts:ro" api python /app/scripts/baseline_metrics.py

test:
	python3 -m pytest tests

lint:
	ruff check services/backend tests

helm-lint:
	helm lint deploy/helm/sam
	helm template sam deploy/helm/sam -f deploy/helm/sam/values-dev.yaml --set existingSecret=sam-secrets >/dev/null

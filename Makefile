.PHONY: dev-env up down logs status config build migrate seed test lint helm-lint

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

migrate seed:
	@echo 'Not implemented: see docs/implementation-plan.md' && exit 1

test:
	python3 -m pytest tests

lint:
	ruff check services/backend tests

helm-lint:
	helm lint deploy/helm/sam
	helm template sam deploy/helm/sam -f deploy/helm/sam/values-dev.yaml --set existingSecret=sam-secrets >/dev/null

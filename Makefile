SHELL := /bin/bash

PROJECT_NAME ?= url-shortener-analytics
VERSION ?= $(shell cat VERSION 2>/dev/null || echo "1.0.0")
REF ?= HEAD

API_PORT ?= 8001
API_BASE_URL ?= http://localhost:$(API_PORT)

DC ?= docker compose

API_SERVICE ?= api
DB_SERVICE ?= db
REDIS_SERVICE ?= redis
WORKER_SERVICE ?= worker
BEAT_SERVICE ?= beat

POSTGRES_USER ?= postgres
POSTGRES_DB ?= urlshort

PYTHON ?= python3

EMAIL ?= local@example.com
PASSWORD ?= password123
API_KEY ?=
URL ?= https://example.com
ALIAS ?= demo
CODES ?=

WEBHOOK_URL ?= http://host.docker.internal:9999/webhook
WEBHOOK_THRESHOLD ?= 3

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo ""
	@echo "$(PROJECT_NAME) — local development commands"
	@echo ""
	@echo "Quick start:"
	@echo "  make setup          Copy .env.example to .env.dev if missing"
	@echo "  make up             Build and start local Docker stack"
	@echo "  make migrate        Run Alembic migrations inside API container"
	@echo "  make health         Check API health"
	@echo "  make open-urls      Print local URLs"
	@echo ""
	@echo "Docker:"
	@echo "  make build          Build Docker images"
	@echo "  make up             Start services in detached mode"
	@echo "  make down           Stop services"
	@echo "  make reset          Stop services and remove volumes"
	@echo "  make ps             Show Docker Compose service status"
	@echo "  make logs           Follow all logs"
	@echo "  make logs-api       Follow API logs"
	@echo "  make logs-worker    Follow worker logs"
	@echo "  make logs-beat      Follow beat logs"
	@echo "  make logs-db        Follow database logs"
	@echo "  make logs-redis     Follow Redis logs"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        Run migrations"
	@echo "  make db-shell       Open psql shell"
	@echo "  make alembic-current"
	@echo "  make alembic-history"
	@echo ""
	@echo "Redis / Celery:"
	@echo "  make redis-cli      Open Redis CLI on DB 0"
	@echo "  make redis-keys     List Redis DB 0 keys"
	@echo "  make worker-ping    Ping Celery worker"
	@echo "  make celery-tasks   List registered Celery tasks"
	@echo ""
	@echo "Quality:"
	@echo "  make format         Run Ruff formatter"
	@echo "  make format-check   Check Ruff formatting"
	@echo "  make lint           Run Ruff lint"
	@echo "  make type           Run mypy"
	@echo "  make test           Run tests locally"
	@echo "  make test-docker    Run tests inside API container"
	@echo "  make quality        Run format-check, lint, mypy, tests"
	@echo ""
	@echo "Smoke tests:"
	@echo "  make smoke          Health + OpenAPI + dashboard HTTP checks"
	@echo "  make openapi        Print first lines of openapi.json"
	@echo "  make dashboard-check"
	@echo ""
	@echo "API helpers:"
	@echo "  make register EMAIL=local@example.com PASSWORD=password123"
	@echo "  make create-link API_KEY=... ALIAS=demo URL=https://example.com"
	@echo "  make click ALIAS=demo"
	@echo "  make stats API_KEY=... ALIAS=demo"
	@echo "  make compare API_KEY=... CODES=code1,code2"
	@echo ""
	@echo "Webhook helper:"
	@echo "  make webhook-receiver"
	@echo "  make create-webhook-link API_KEY=... ALIAS=webhookdemo"
	@echo ""
	@echo "Release artifacts:"
	@echo "  make archive-zip REF=v1.0.0"
	@echo "  make archive-tar REF=v1.0.0"
	@echo "  make bundle"
	@echo ""

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

.PHONY: setup
setup:
	@if [ ! -f .env.dev ]; then \
	  if [ -f .env.example ]; then \
	    cp .env.example .env.dev; \
	    echo "Created .env.dev from .env.example"; \
	  else \
	    echo "ERROR: .env.example not found"; \
	    exit 1; \
	  fi \
	else \
	  echo ".env.dev already exists"; \
	fi

.PHONY: doctor
doctor:
	@echo "Checking local tools..."
	@command -v git >/dev/null 2>&1 && echo "git: ok" || (echo "git: missing" && exit 1)
	@command -v docker >/dev/null 2>&1 && echo "docker: ok" || (echo "docker: missing" && exit 1)
	@docker compose version >/dev/null 2>&1 && echo "docker compose: ok" || (echo "docker compose: missing" && exit 1)
	@command -v $(PYTHON) >/dev/null 2>&1 && echo "$(PYTHON): ok" || echo "$(PYTHON): missing or not in PATH"

.PHONY: open-urls
open-urls:
	@echo ""
	@echo "Local URLs:"
	@echo "  Health:    $(API_BASE_URL)/health"
	@echo "  Swagger:   $(API_BASE_URL)/docs"
	@echo "  ReDoc:     $(API_BASE_URL)/redoc"
	@echo "  OpenAPI:   $(API_BASE_URL)/openapi.json"
	@echo "  Dashboard: $(API_BASE_URL)/dashboard"
	@echo ""

.PHONY: first-run
first-run: setup up migrate smoke open-urls

# -------------------------------------------------------------------
# Docker
# -------------------------------------------------------------------

.PHONY: build
build:
	$(DC) build

.PHONY: up
up:
	$(DC) up --build -d

.PHONY: down
down:
	$(DC) down

.PHONY: reset
reset:
	$(DC) down -v

.PHONY: restart
restart:
	$(DC) down
	$(DC) up --build -d

.PHONY: ps
ps:
	$(DC) ps

.PHONY: logs
logs:
	$(DC) logs -f

.PHONY: logs-api
logs-api:
	$(DC) logs -f $(API_SERVICE)

.PHONY: logs-worker
logs-worker:
	$(DC) logs -f $(WORKER_SERVICE)

.PHONY: logs-beat
logs-beat:
	$(DC) logs -f $(BEAT_SERVICE)

.PHONY: logs-db
logs-db:
	$(DC) logs -f $(DB_SERVICE)

.PHONY: logs-redis
logs-redis:
	$(DC) logs -f $(REDIS_SERVICE)

# -------------------------------------------------------------------
# Database / Alembic
# -------------------------------------------------------------------

.PHONY: migrate
migrate:
	@if $(DC) config --services | grep -qx "migrate"; then \
	  $(DC) run --rm migrate; \
	else \
	  $(DC) exec $(API_SERVICE) alembic upgrade head; \
	fi

.PHONY: alembic-current
alembic-current:
	$(DC) exec $(API_SERVICE) alembic current

.PHONY: alembic-history
alembic-history:
	$(DC) exec $(API_SERVICE) alembic history

.PHONY: db-shell
db-shell:
	$(DC) exec $(DB_SERVICE) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

# -------------------------------------------------------------------
# Redis / Celery
# -------------------------------------------------------------------

.PHONY: redis-cli
redis-cli:
	$(DC) exec $(REDIS_SERVICE) redis-cli -n 0

.PHONY: redis-keys
redis-keys:
	$(DC) exec $(REDIS_SERVICE) redis-cli -n 0 keys '*'

.PHONY: redis-keyspace
redis-keyspace:
	$(DC) exec $(REDIS_SERVICE) redis-cli info keyspace

.PHONY: worker-ping
worker-ping:
	$(DC) exec $(WORKER_SERVICE) celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5

.PHONY: celery-tasks
celery-tasks:
	$(DC) exec $(WORKER_SERVICE) celery -A app.tasks.celery_app:celery_app inspect registered

# -------------------------------------------------------------------
# Quality
# -------------------------------------------------------------------

.PHONY: format
format:
	uv run ruff format .

.PHONY: format-check
format-check:
	uv run ruff format --check .

.PHONY: lint
lint:
	uv run ruff check .

.PHONY: type
type:
	uv run mypy app/

.PHONY: test
test:
	uv run pytest -v

.PHONY: test-docker
test-docker:
	$(DC) exec $(API_SERVICE) uv run pytest -v

.PHONY: quality
quality: format-check lint type test

.PHONY: pre-commit
pre-commit:
	uv run pre-commit run --all-files

# -------------------------------------------------------------------
# Smoke tests
# -------------------------------------------------------------------

.PHONY: health
health:
	curl -i $(API_BASE_URL)/health

.PHONY: openapi
openapi:
	curl -s $(API_BASE_URL)/openapi.json | $(PYTHON) -m json.tool | head -40

.PHONY: dashboard-check
dashboard-check:
	@code=$$(curl -s -o /dev/null -w "%{http_code}" $(API_BASE_URL)/dashboard); \
	echo "Dashboard HTTP $$code"; \
	test "$$code" = "200"

.PHONY: docs-check
docs-check:
	@docs_code=$$(curl -s -o /dev/null -w "%{http_code}" $(API_BASE_URL)/docs); \
	redoc_code=$$(curl -s -o /dev/null -w "%{http_code}" $(API_BASE_URL)/redoc); \
	openapi_code=$$(curl -s -o /dev/null -w "%{http_code}" $(API_BASE_URL)/openapi.json); \
	echo "Swagger HTTP $$docs_code"; \
	echo "ReDoc HTTP $$redoc_code"; \
	echo "OpenAPI HTTP $$openapi_code"; \
	test "$$docs_code" = "200"; \
	test "$$redoc_code" = "200"; \
	test "$$openapi_code" = "200"

.PHONY: smoke
smoke:
	@health_code=$$(curl -Ls -o /dev/null -w "%{http_code}" $(API_BASE_URL)/health); \
	docs_code=$$(curl -Ls -o /dev/null -w "%{http_code}" $(API_BASE_URL)/docs); \
	redoc_code=$$(curl -Ls -o /dev/null -w "%{http_code}" $(API_BASE_URL)/redoc); \
	openapi_code=$$(curl -Ls -o /dev/null -w "%{http_code}" $(API_BASE_URL)/openapi.json); \
	dashboard_code=$$(curl -Ls -o /dev/null -w "%{http_code}" $(API_BASE_URL)/dashboard); \
	echo "Health HTTP $$health_code"; \
	echo "Swagger HTTP $$docs_code"; \
	echo "ReDoc HTTP $$redoc_code"; \
	echo "OpenAPI HTTP $$openapi_code"; \
	echo "Dashboard HTTP $$dashboard_code"; \
	test "$$health_code" = "200"; \
	test "$$docs_code" = "200"; \
	test "$$redoc_code" = "200"; \
	test "$$openapi_code" = "200"; \
	test "$$dashboard_code" = "200"


# -------------------------------------------------------------------
# API helpers
# -------------------------------------------------------------------

.PHONY: register
register:
	curl -s -X POST $(API_BASE_URL)/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"email": "$(EMAIL)", "password": "$(PASSWORD)"}' \
	  | $(PYTHON) -m json.tool

.PHONY: create-link
create-link:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  echo "Usage: make create-link API_KEY=... ALIAS=demo URL=https://example.com"; \
	  exit 1; \
	fi
	curl -s -X POST $(API_BASE_URL)/api/v1/links \
	  -H "X-API-Key: $(API_KEY)" \
	  -H "Content-Type: application/json" \
	  -d '{"long_url": "$(URL)", "custom_alias": "$(ALIAS)"}' \
	  | $(PYTHON) -m json.tool

.PHONY: click
click:
	curl -i $(API_BASE_URL)/$(ALIAS)

.PHONY: links
links:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  echo "Usage: make links API_KEY=..."; \
	  exit 1; \
	fi
	curl -s "$(API_BASE_URL)/api/v1/links?limit=10" \
	  -H "X-API-Key: $(API_KEY)" \
	  | $(PYTHON) -m json.tool

.PHONY: stats
stats:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  echo "Usage: make stats API_KEY=... ALIAS=demo"; \
	  exit 1; \
	fi
	curl -s "$(API_BASE_URL)/api/v1/analytics/links/$(ALIAS)/timeseries?days=7" \
	  -H "X-API-Key: $(API_KEY)" \
	  | $(PYTHON) -m json.tool

.PHONY: breakdown-country
breakdown-country:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  exit 1; \
	fi
	curl -s "$(API_BASE_URL)/api/v1/analytics/links/$(ALIAS)/breakdown?dimension=country" \
	  -H "X-API-Key: $(API_KEY)" \
	  | $(PYTHON) -m json.tool

.PHONY: breakdown-browser
breakdown-browser:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  exit 1; \
	fi
	curl -s "$(API_BASE_URL)/api/v1/analytics/links/$(ALIAS)/breakdown?dimension=browser" \
	  -H "X-API-Key: $(API_KEY)" \
	  | $(PYTHON) -m json.tool

.PHONY: breakdown-referrer
breakdown-referrer:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  exit 1; \
	fi
	curl -s "$(API_BASE_URL)/api/v1/analytics/links/$(ALIAS)/breakdown?dimension=referrer" \
	  -H "X-API-Key: $(API_KEY)" \
	  | $(PYTHON) -m json.tool

.PHONY: compare
compare:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  echo "Usage: make compare API_KEY=... CODES=code1,code2"; \
	  exit 1; \
	fi
	@if [ -z "$(CODES)" ]; then \
	  echo "ERROR: CODES is required"; \
	  echo "Usage: make compare API_KEY=... CODES=code1,code2"; \
	  exit 1; \
	fi
	curl -s "$(API_BASE_URL)/api/v1/analytics/compare?codes=$(CODES)&days=7" \
	  -H "X-API-Key: $(API_KEY)" \
	  | $(PYTHON) -m json.tool

# -------------------------------------------------------------------
# Webhook local receiver
# -------------------------------------------------------------------

.PHONY: webhook-receiver
webhook-receiver:
	$(PYTHON) - <<'PY'
	from http.server import BaseHTTPRequestHandler, HTTPServer

	class Handler(BaseHTTPRequestHandler):
	    def do_POST(self):
	        n = int(self.headers.get("Content-Length", "0"))
	        body = self.rfile.read(n)
	        print("\n--- Webhook received ---")
	        print("PATH:", self.path)
	        print("SIGNATURE:", self.headers.get("X-Webhook-Signature"))
	        print("EVENT:", self.headers.get("X-Webhook-Event"))
	        print("BODY:", body.decode())
	        self.send_response(200)
	        self.end_headers()
	        self.wfile.write(b"ok")

	    def log_message(self, *_):
	        pass

	print("Listening on http://0.0.0.0:9999/webhook")
	HTTPServer(("0.0.0.0", 9999), Handler).serve_forever()
	PY

.PHONY: create-webhook-link
create-webhook-link:
	@if [ -z "$(API_KEY)" ]; then \
	  echo "ERROR: API_KEY is required"; \
	  echo "Usage: make create-webhook-link API_KEY=... ALIAS=webhookdemo"; \
	  exit 1; \
	fi
	curl -s -X POST $(API_BASE_URL)/api/v1/links \
	  -H "X-API-Key: $(API_KEY)" \
	  -H "Content-Type: application/json" \
	  -d '{"long_url": "$(URL)", "custom_alias": "$(ALIAS)", "webhook_url": "$(WEBHOOK_URL)", "webhook_threshold": $(WEBHOOK_THRESHOLD)}' \
	  | $(PYTHON) -m json.tool

.PHONY: webhook-clicks
webhook-clicks:
	for i in 1 2 3 4; do \
	  curl -s -o /dev/null -w "%{http_code}\n" "$(API_BASE_URL)/$(ALIAS)"; \
	done

# -------------------------------------------------------------------
# GeoIP
# -------------------------------------------------------------------

.PHONY: geoip-check
geoip-check:
	$(DC) exec -T $(WORKER_SERVICE) python - <<'PY'
	from app.services.geoip import lookup_geoip

	for ip in ["8.8.8.8", "1.1.1.1", "81.2.69.142", "127.0.0.1"]:
	    print(ip, lookup_geoip(ip))
	PY

# -------------------------------------------------------------------
# Release artifacts
# -------------------------------------------------------------------

.PHONY: archive-zip
archive-zip:
	git archive \
	  --format=zip \
	  --output ../$(PROJECT_NAME)-v$(VERSION).zip \
	  $(REF)
	@echo "Created ../$(PROJECT_NAME)-v$(VERSION).zip from $(REF)"

.PHONY: archive-tar
archive-tar:
	git archive \
	  --format=tar.gz \
	  --prefix=$(PROJECT_NAME)-v$(VERSION)/ \
	  --output ../$(PROJECT_NAME)-v$(VERSION).tar.gz \
	  $(REF)
	@echo "Created ../$(PROJECT_NAME)-v$(VERSION).tar.gz from $(REF)"

.PHONY: bundle
bundle:
	git bundle create ../$(PROJECT_NAME)-v$(VERSION).bundle --all
	@echo "Created ../$(PROJECT_NAME)-v$(VERSION).bundle"

.PHONY: release-artifacts
release-artifacts: archive-zip archive-tar bundle

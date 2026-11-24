# SolidarityNode developer commands. Run `make help` for the list.
#
# Container engine: Podman by default, Docker supported. Override from the environment:
#   CONTAINER_ENGINE=docker COMPOSE="docker compose" make up
# Never hard-code an engine elsewhere; use these variables.

CONTAINER_ENGINE ?= podman
COMPOSE ?= podman compose
UV ?= uv
PNPM ?= pnpm

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV_RUN := $(UV) run --frozen

# Host ports and other values from .env (if present), with the same defaults as compose.yaml.
-include .env
BACKEND_HOST_PORT ?= 8000
FRONTEND_HOST_PORT ?= 8080
APP_ENV ?= development

# Build identity shown by /version and the frontend footer.
GIT_COMMIT ?= $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)$(shell git diff --quiet HEAD 2>/dev/null || echo -dirty)
export GIT_COMMIT

FRONTEND_URL := http://127.0.0.1:$(FRONTEND_HOST_PORT)
BACKEND_URL := http://127.0.0.1:$(BACKEND_HOST_PORT)

.PHONY: help check-tools check-engine env check-config setup setup-core setup-backend setup-frontend \
        lint lint-core lint-backend lint-frontend \
        test test-core test-backend test-frontend \
        fmt stop up down logs ps wait db-shell seed reset uat images licenses labels clean distclean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------------------

check-tools: ## Check that uv, node and pnpm are on PATH
	@missing=""; \
	for tool in $(UV) node $(PNPM); do command -v "$$tool" >/dev/null 2>&1 || missing="$$missing $$tool"; done; \
	if [ -n "$$missing" ]; then \
	  echo "Missing required tools:$$missing" >&2; \
	  echo "Install them (see CONTRIBUTING.md, Setup) and make sure they are on PATH," >&2; \
	  echo "for example by opening a new login shell." >&2; \
	  exit 1; \
	fi

check-engine:
	@command -v $(CONTAINER_ENGINE) >/dev/null 2>&1 || { \
	  echo "Container engine '$(CONTAINER_ENGINE)' not found. Install it or set CONTAINER_ENGINE and COMPOSE." >&2; exit 1; }
	@$(COMPOSE) version >/dev/null 2>&1 || { \
	  echo "Compose command '$(COMPOSE)' does not work. Install it or set COMPOSE." >&2; exit 1; }

setup: check-tools env setup-core setup-backend setup-frontend ## Install all dependencies (locked)

env: ## Create .env from .env.example if missing; warn about missing keys
	@scripts/ensure-env.sh .env.example .env

check-config: check-engine ## Validate backend settings in a one-off container (e.g. APP_ENV=production)
	$(COMPOSE) run --rm --no-deps -e APP_ENV=$(APP_ENV) backend \
	  python -c "from solidaritynode_backend.config import Settings; s = Settings(); print(f'configuration OK (APP_ENV={s.app_env})')"

setup-core:
	cd core && $(UV) sync --locked

setup-backend:
	cd backend && $(UV) sync --locked

setup-frontend:
	cd frontend && $(PNPM) install --frozen-lockfile

# --- Lint and type check -----------------------------------------------------------------

lint: lint-core lint-backend lint-frontend ## ruff, mypy, eslint, prettier, tsc

lint-core:
	cd core && $(UV_RUN) ruff check . && $(UV_RUN) ruff format --check . && $(UV_RUN) mypy

lint-backend:
	cd backend && $(UV_RUN) ruff check . && $(UV_RUN) ruff format --check . && $(UV_RUN) mypy

lint-frontend:
	cd frontend && $(PNPM) run lint && $(PNPM) run typecheck

# --- Tests ---------------------------------------------------------------------------------

test: test-core test-backend test-frontend ## Run all tests

test-core:
	cd core && $(UV_RUN) pytest

test-backend:
	cd backend && $(UV_RUN) pytest

test-frontend:
	cd frontend && $(PNPM) run test

# --- Formatting ----------------------------------------------------------------------------

fmt: ## Auto-format and auto-fix (ruff, prettier, eslint)
	cd core && $(UV_RUN) ruff check --fix . && $(UV_RUN) ruff format .
	cd backend && $(UV_RUN) ruff check --fix . && $(UV_RUN) ruff format .
	cd frontend && $(PNPM) run fmt

# --- Containers ----------------------------------------------------------------------------

stop: ## Stop one service, keep the others (SERVICE=backend|frontend|db)
	@[ -n "$(SERVICE)" ] || { echo "Usage: make stop SERVICE=backend|frontend|db" >&2; exit 1; }
	$(COMPOSE) stop $(SERVICE)

up: check-engine ## Build and start db, backend and frontend with $(COMPOSE)
	$(COMPOSE) up -d --build
	@echo "Build $(GIT_COMMIT). Frontend: $(FRONTEND_URL)  Backend: $(BACKEND_URL)/health"

down: ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

logs: ## Follow container logs
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

wait: ## Wait until the backend reports ready (database reachable)
	@echo "Waiting for the backend to become ready..."
	@for i in $$(seq 1 60); do \
	  if $(COMPOSE) exec -T backend python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).status == 200 else 1)" >/dev/null 2>&1; then \
	    echo "Backend ready."; exit 0; \
	  fi; \
	  sleep 2; \
	done; \
	echo "Backend not ready after 120 s. Check 'make logs'." >&2; exit 1

db-shell: ## Open psql in the database container (credentials from .env; also reads SQL from stdin)
	$(COMPOSE) exec $$([ -t 0 ] || echo -T) db sh -c 'exec psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

seed: ## Load the synthetic demo dataset into schema 'demo' (idempotent)
	$(COMPOSE) exec -T backend python -m solidaritynode_backend.demo_seed

reset: check-engine ## DELETE the database volume, restart, migrate and seed (asks unless FORCE=1)
	@if [ "$(FORCE)" != "1" ]; then \
	  echo "This stops the stack and DELETES the database volume (all local data)."; \
	  read -r -p "Type 'yes' to continue: " answer || answer=""; \
	  [ "$$answer" = "yes" ] || { echo "Aborted."; exit 1; }; \
	fi
	$(COMPOSE) down --volumes
	$(MAKE) --no-print-directory up
	$(MAKE) --no-print-directory wait
	$(COMPOSE) exec -T backend alembic upgrade head
	$(MAKE) --no-print-directory seed

uat: ## Fresh state for manual testing: reset, up, then print the URLs to open
	$(MAKE) --no-print-directory reset
	$(MAKE) --no-print-directory up
	$(MAKE) --no-print-directory wait
	@echo ""
	@echo "UAT environment ready (build $(GIT_COMMIT)). Open:"
	@echo "  Frontend:       $(FRONTEND_URL)"
	@echo "  Health page:    $(FRONTEND_URL)/health"
	@echo "  Backend docs:   $(BACKEND_URL)/docs"
	@echo "  Backend health: $(BACKEND_URL)/health"
	@echo "  Version:        $(BACKEND_URL)/version"
	@echo "Checklist: docs/uat/00-bootstrap.md. Database: make db-shell. Logs: make logs."

images: ## Build the container images with $(CONTAINER_ENGINE)
	$(CONTAINER_ENGINE) build -f backend/Containerfile -t localhost/solidaritynode-backend:dev .
	$(CONTAINER_ENGINE) build -f frontend/Containerfile -t localhost/solidaritynode-frontend:dev frontend

# --- Repository automation -----------------------------------------------------------------

licenses: ## Fail on dependency licences incompatible with AGPL-3.0
	cd core && $(UV_RUN) python ../scripts/check_licenses.py python
	cd backend && $(UV_RUN) python ../scripts/check_licenses.py python
	cd frontend && $(PNPM) licenses list --json --long | python3 ../scripts/check_licenses.py pnpm

labels: ## Create or update GitHub labels from .github/labels.yml (needs gh auth)
	scripts/create-labels.sh

# --- Cleaning ------------------------------------------------------------------------------

clean: ## Remove caches and build output
	rm -rf core/.pytest_cache core/.mypy_cache core/.ruff_cache \
	       backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache \
	       frontend/dist frontend/coverage frontend/node_modules/.tmp
	find core backend -type d -name __pycache__ -prune -exec rm -rf {} +

distclean: clean ## Also remove virtual environments and node_modules
	rm -rf core/.venv backend/.venv frontend/node_modules

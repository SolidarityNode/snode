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
# APP_ENV from the shell wins over .env, as it does for compose, so check-config validates
# what compose will actually start.
SHELL_APP_ENV := $(APP_ENV)
-include .env
ifneq ($(SHELL_APP_ENV),)
APP_ENV := $(SHELL_APP_ENV)
endif
BACKEND_HOST_PORT ?= 8000
FRONTEND_HOST_PORT ?= 8080
APP_ENV ?= development
export APP_ENV

# Build identity shown by /version and the frontend footer.
GIT_COMMIT ?= $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)$(shell git diff --quiet HEAD 2>/dev/null || echo -dirty)
export GIT_COMMIT

FRONTEND_URL := http://127.0.0.1:$(FRONTEND_HOST_PORT)
BACKEND_URL := http://127.0.0.1:$(BACKEND_HOST_PORT)

.PHONY: help check-tools check-engine env check-config setup setup-core setup-backend setup-frontend \
        lint lint-repo lint-core lint-backend lint-frontend \
        test test-core test-backend test-frontend \
        fmt stop up down logs ps wait db-shell seed reset uat images licenses labels clean distclean \
        test-db test-e2e e2e-setup import-package activate-version create-admin schemas \
        clear-login-locks version version-sync docs docs-setup docs-build docs-generate docs-check docs-stamp docs-links \
        deps-report deps-report-check

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
	@$(COMPOSE) run --rm --no-deps -e APP_ENV=$(APP_ENV) backend \
	  python -m solidaritynode_backend.cli check-config

setup-core:
	cd core && $(UV) sync --locked

setup-backend:
	cd backend && $(UV) sync --locked

setup-frontend:
	cd frontend && $(PNPM) install --frozen-lockfile

# --- Lint and type check -----------------------------------------------------------------

lint: lint-core lint-backend lint-frontend lint-repo ## ruff, mypy, eslint, prettier, tsc, version and generated docs

lint-repo:
	python3 scripts/version.py check
	python3 scripts/docs_indexes.py --check
	python3 scripts/docs_i18n.py --check

lint-core:
	cd core && $(UV_RUN) ruff check . && $(UV_RUN) ruff format --check . && $(UV_RUN) mypy

lint-backend:
	cd backend && $(UV_RUN) ruff check . && $(UV_RUN) ruff format --check . && $(UV_RUN) mypy

lint-frontend:
	cd frontend && $(PNPM) run lint && $(PNPM) run typecheck

# --- Tests ---------------------------------------------------------------------------------

# `make test` is fast and needs no container engine: unit and integration tests only. The
# end-to-end test runs with `make test-e2e` and in CI.
test: test-core test-backend test-frontend ## Unit and integration tests (backend needs PostGIS: make test-db)

test-core:
	cd core && $(UV_RUN) pytest

# Backend tests need PostGIS: they create and drop a throw-away database on the server given by
# SOLIDARITYNODE_TEST_DATABASE_URL (default: the compose `db` service on 127.0.0.1:5432, as left
# running by `make up` or `make test-db`). `make test-backend` does not start containers.
test-db: ## Start the database used by the backend tests (skipped if SOLIDARITYNODE_TEST_DATABASE_URL is set)
	@if [ -z "$${SOLIDARITYNODE_TEST_DATABASE_URL:-}" ]; then \
	  $(MAKE) --no-print-directory check-engine && $(COMPOSE) up -d db && \
	  for i in $$(seq 1 60); do \
	    $(COMPOSE) exec -T db sh -c 'pg_isready -q -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' && exit 0; sleep 1; \
	  done; echo "Database not ready." >&2; exit 1; \
	fi

test-backend:
	cd backend && $(UV_RUN) pytest

test-frontend:
	cd frontend && $(PNPM) run test

# The end-to-end test runs in its own throw-away stack (compose project $(E2E_PROJECT), its own
# volumes and ports), so it always starts from demo package 1.0.0 and never touches your local
# data; the stack is removed afterwards. Playwright runs in its official image (browsers and
# system libraries included) on the host network. E2E_LOCAL=1 uses a host browser instead
# (`make e2e-setup` once).
PLAYWRIGHT_IMAGE ?= mcr.microsoft.com/playwright:v1.65.1-noble
E2E_PROJECT ?= solidaritynode-e2e
E2E_FRONTEND_PORT ?= 18080
E2E_BACKEND_PORT ?= 18000
E2E_DB_PORT ?= 15432
E2E_COMPOSE := $(COMPOSE) -p $(E2E_PROJECT)
E2E_URL := http://127.0.0.1:$(E2E_FRONTEND_PORT)

e2e-setup: ## Install the Playwright browser on the host (only for E2E_LOCAL=1)
	cd frontend && $(PNPM) exec playwright install chromium

test-e2e: check-engine ## End-to-end test (Playwright) in a separate throw-away stack
	$(E2E_COMPOSE) down --volumes >/dev/null 2>&1 || true
	@status=0; \
	$(MAKE) --no-print-directory up wait seed COMPOSE="$(E2E_COMPOSE)" \
	  FRONTEND_HOST_PORT=$(E2E_FRONTEND_PORT) BACKEND_HOST_PORT=$(E2E_BACKEND_PORT) \
	  DB_HOST_PORT=$(E2E_DB_PORT) || status=$$?; \
	if [ $$status -eq 0 ]; then \
	  if [ "$(E2E_LOCAL)" = "1" ]; then \
	    (cd frontend && E2E_BASE_URL=$(E2E_URL) $(PNPM) run test:e2e) || status=$$?; \
	  else \
	    $(CONTAINER_ENGINE) run --rm --network host -v "$(CURDIR)/frontend:/work:Z" -w /work \
	      -e E2E_BASE_URL=$(E2E_URL) $(PLAYWRIGHT_IMAGE) npx playwright test || status=$$?; \
	  fi; \
	fi; \
	FRONTEND_HOST_PORT=$(E2E_FRONTEND_PORT) BACKEND_HOST_PORT=$(E2E_BACKEND_PORT) DB_HOST_PORT=$(E2E_DB_PORT) \
	  $(E2E_COMPOSE) down --volumes >/dev/null 2>&1 || true; \
	exit $$status

# --- Formatting ----------------------------------------------------------------------------

fmt: ## Auto-format and auto-fix (ruff, prettier, eslint)
	cd core && $(UV_RUN) ruff check --fix . && $(UV_RUN) ruff format .
	cd backend && $(UV_RUN) ruff check --fix . && $(UV_RUN) ruff format .
	cd frontend && $(PNPM) run fmt

# --- Containers ----------------------------------------------------------------------------

stop: ## Stop one service, keep the others (SERVICE=backend|worker|frontend|db)
	@[ -n "$(SERVICE)" ] || { echo "Usage: make stop SERVICE=backend|worker|frontend|db" >&2; exit 1; }
	$(COMPOSE) stop $(SERVICE)

up: check-engine ## Build, validate the configuration (check-config), then start the stack
	$(COMPOSE) build
	@$(MAKE) --no-print-directory check-config || { \
	  echo "make up: invalid configuration (see the message above); nothing was started." >&2; exit 1; }
	$(COMPOSE) up -d
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

seed: ## Import demo package 1.0.0 (no-op if present), demo users (development), wait for runs
	$(COMPOSE) exec -T backend python -m solidaritynode_backend.cli import-package /app/data/synthetic/packages/demo-1.0.0 --yes
	@if [ "$(APP_ENV)" = "development" ]; then \
	  $(COMPOSE) exec -T backend python -m solidaritynode_backend.cli seed-demo-users; \
	else echo "APP_ENV=$(APP_ENV): demo users not created."; fi
	$(COMPOSE) exec -T backend python -m solidaritynode_backend.cli wait-runs --timeout 180

import-package: check-engine ## Validate, preview and import a data package (PKG=dir or archive; YES=1 skips the question)
	@[ -n "$(PKG)" ] || { echo "Usage: make import-package PKG=<directory or .zip/.tar.gz>" >&2; exit 1; }
	@[ -e "$(PKG)" ] || { echo "make import-package: $(PKG) not found" >&2; exit 1; }
	@pack() { if [ -d "$(PKG)" ]; then tar -C "$(PKG)" -cf - .; else cat "$(PKG)"; fi; }; \
	rc=0; pack | $(COMPOSE) exec -T backend python -m solidaritynode_backend.cli import-package - --preview-only || rc=$$?; \
	[ $$rc -eq 3 ] && exit 0; [ $$rc -eq 0 ] || exit $$rc; \
	if [ "$(YES)" != "1" ]; then \
	  read -r -p "Import this package? Type 'yes' to confirm: " answer || answer=""; \
	  [ "$$answer" = "yes" ] || { echo "Aborted; nothing imported."; exit 1; }; \
	fi; \
	pack | $(COMPOSE) exec -T backend python -m solidaritynode_backend.cli import-package - --yes

activate-version: check-engine ## Make an earlier imported data version active again (VERSION=x.y.z; YES=1 skips the question)
	@[ -n "$(VERSION)" ] || { echo "Usage: make activate-version VERSION=<x.y.z> [PACKAGE_ID=...]" >&2; exit 1; }
	@args="$(VERSION)$(if $(PACKAGE_ID), --package-id $(PACKAGE_ID),)"; \
	rc=0; $(COMPOSE) exec -T backend python -m solidaritynode_backend.cli activate-version $$args || rc=$$?; \
	[ $$rc -eq 3 ] && exit 0; [ $$rc -eq 0 ] || exit $$rc; \
	if [ "$(YES)" != "1" ]; then \
	  read -r -p "Make it active? Type 'yes' to confirm: " answer || answer=""; \
	  [ "$$answer" = "yes" ] || { echo "Aborted; nothing changed."; exit 1; }; \
	fi; \
	$(COMPOSE) exec -T backend python -m solidaritynode_backend.cli activate-version $$args --yes

clear-login-locks: check-engine ## Clear sign-in locks: USERNAME=<name>, or all when not set
	$(COMPOSE) exec -T backend python -m solidaritynode_backend.cli clear-login-locks \
	  $(if $(USERNAME),--username "$(USERNAME)",--all)

create-admin: check-engine ## Create the first administrator interactively
	$(COMPOSE) exec backend python -m solidaritynode_backend.cli create-admin

schemas: ## Export the scenario JSON Schema, OpenAPI and message templates; regenerate frontend API types
	cd backend && $(UV_RUN) python -m solidaritynode_backend.cli export-schemas ../docs/schemas
	cp docs/schemas/messages.json frontend/src/api/messages.json
	cd frontend && $(PNPM) run gen:api

reset: check-engine ## DELETE the database and results volumes, restart, migrate and seed (asks unless FORCE=1)
	@if [ "$(FORCE)" != "1" ]; then \
	  echo "This stops the stack and DELETES the database and results volumes (all local data)."; \
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
	@echo "UAT environment ready (build $(GIT_COMMIT)). Demo package 1.0.0 imported, baseline run done."
	@echo "Open:"
	@echo "  Application:    $(FRONTEND_URL)"
	@echo "  Health page:    $(FRONTEND_URL)/health"
	@echo "  Backend docs:   $(BACKEND_URL)/docs"
	@echo "  Version:        $(BACKEND_URL)/version"
	@echo "Demo accounts (development only):"
	@echo "  demo-admin   / demo-admin-pass    (admin: users and data packages)"
	@echo "  demo-analyst / demo-analyst-pass  (analyst: scenarios and runs)"
	@echo "Checklist: docs/uat/01-platform.md. Database: make db-shell. Logs: make logs."

images: ## Build the container images with $(CONTAINER_ENGINE)
	$(CONTAINER_ENGINE) build -f backend/Containerfile -t localhost/solidaritynode-backend:dev .
	$(CONTAINER_ENGINE) build -f frontend/Containerfile -t localhost/solidaritynode-frontend:dev frontend

# --- Documentation -------------------------------------------------------------------------

DOCS_RUN := cd tools/docs && $(UV_RUN)
DOCS_PORT ?= 8001
LYCHEE_IMAGE ?= docker.io/lycheeverse/lychee:0.24.2

docs-setup: ## Install the locked documentation tooling (MkDocs, Material, mike)
	cd tools/docs && $(UV) sync --locked

docs: docs-setup ## Serve the documentation site on http://127.0.0.1:$(DOCS_PORT) with live reload
	$(DOCS_RUN) mkdocs serve -f ../../mkdocs.yml -a 127.0.0.1:$(DOCS_PORT)

docs-build: docs-setup docs-check ## Build the documentation site into site/ with --strict
	$(DOCS_RUN) mkdocs build --strict -f ../../mkdocs.yml

docs-generate: ## Regenerate the ADR index, specs index and open-question counts
	python3 scripts/docs_indexes.py

docs-check: ## Check the generated docs blocks, the version and the Greek pages are current
	python3 scripts/version.py check
	python3 scripts/docs_indexes.py --check
	python3 scripts/docs_i18n.py --check

docs-stamp: ## Record that a Greek page matches its English source again (PAGE=docs/x.el.md)
	@test -n "$(PAGE)" || { echo "usage: make docs-stamp PAGE=docs/user-guide/run.el.md" >&2; exit 1; }
	python3 scripts/docs_i18n.py --stamp $(PAGE)

docs-links: check-engine ## Check links in README and docs with lychee (container; also in CI)
	$(CONTAINER_ENGINE) run --rm -v "$(CURDIR):/input:ro,Z" -w /input $(LYCHEE_IMAGE) \
	  --config lychee.toml README.md CHANGELOG.md CONTRIBUTING.md 'docs/**/*.md'

deps-report: docs-setup ## Regenerate docs/architecture/dependencies.md from the lock files (needs make setup)
	PNPM=$(PNPM) python3 scripts/deps_report.py

deps-report-check: docs-setup ## Fail if dependencies.md is out of date or a licence is not allowed
	PNPM=$(PNPM) python3 scripts/deps_report.py --check

# --- Repository automation -----------------------------------------------------------------

licenses: ## Fail on dependency licences incompatible with AGPL-3.0
	cd core && $(UV_RUN) python ../scripts/check_licenses.py python
	cd backend && $(UV_RUN) python ../scripts/check_licenses.py python
	cd tools/docs && $(UV_RUN) python ../../scripts/check_licenses.py python
	cd frontend && $(PNPM) licenses list --json --long | python3 ../scripts/check_licenses.py pnpm

version: ## Print the platform version (single source: the VERSION file)
	@python3 scripts/version.py

version-sync: ## Write VERSION into pyproject.toml, package.json and the uv locks
	python3 scripts/version.py sync
	cd core && $(UV) lock
	cd backend && $(UV) lock

labels: ## Create or update GitHub labels from .github/labels.yml (needs gh auth)
	scripts/create-labels.sh

# --- Cleaning ------------------------------------------------------------------------------

clean: ## Remove caches and build output
	rm -rf site core/.pytest_cache core/.mypy_cache core/.ruff_cache \
	       backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache \
	       frontend/dist frontend/coverage frontend/node_modules/.tmp
	find core backend -type d -name __pycache__ -prune -exec rm -rf {} +

distclean: clean ## Also remove virtual environments and node_modules
	rm -rf core/.venv backend/.venv tools/docs/.venv frontend/node_modules

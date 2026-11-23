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

.PHONY: help setup setup-core setup-backend setup-frontend \
        lint lint-core lint-backend lint-frontend \
        test test-core test-backend test-frontend \
        fmt up down logs ps images licenses labels clean distclean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------------------

setup: setup-core setup-backend setup-frontend ## Install all dependencies (locked)

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

up: ## Build and start db, backend and frontend with $(COMPOSE)
	$(COMPOSE) up -d --build
	@echo "Frontend: http://localhost:$${FRONTEND_HOST_PORT:-8080}  Backend: http://localhost:$${BACKEND_HOST_PORT:-8000}/health"

down: ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

logs: ## Follow container logs
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

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

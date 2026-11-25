# solidaritynode-backend

FastAPI service for SolidarityNode. Depends on `core` through a local path dependency; `core`
never depends on the backend.

```bash
uv sync --locked                                   # install (includes ../core)
uv run pytest                                      # tests (need PostGIS: `make test-db`)
uv run python -m solidaritynode_backend.worker      # the background worker
uv run python -m solidaritynode_backend.cli --help  # import-package, create-admin, …
uv run uvicorn solidaritynode_backend.main:app --reload --port 8000
uv run alembic upgrade head                        # migrations (needs PostgreSQL/PostGIS)
```

Configuration comes from environment variables prefixed `SOLIDARITYNODE_` (see `.env.example`
at the repository root), plus `APP_ENV` (`development` | `test` | `production`) and `GIT_COMMIT`
(set at image build). Outside `development` and `test`, the backend refuses to start while any
secret still starts with `change-me`. The test suite runs with `APP_ENV=test`.

Endpoints (OpenAPI at `/docs`, exported to `docs/schemas/openapi.json`): health and version,
`/config`, `/auth/*` (local accounts, ADR 0015), `/users` (admin), `/data-versions` and
`/packages/*` (package preview and import, ADR 0013), `/scenarios` (versioned overlays, ADR 0016),
`/runs` (start, status, cancel, results, compare, export; ADR 0017). The `requests` (tickets)
router stays a placeholder until ADR 0010 (OQ-21, OQ-29). Runs are queued as jobs in
PostgreSQL and executed by the worker (ADR 0006), never inside a request handler.

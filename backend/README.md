# solidaritynode-backend

FastAPI service for SolidarityNode. Depends on `core` through a local path dependency; `core`
never depends on the backend.

```bash
uv sync --locked                                   # install (includes ../core)
uv run pytest                                      # tests (no database needed)
uv run uvicorn solidaritynode_backend.main:app --reload --port 8000
uv run alembic upgrade head                        # migrations (needs PostgreSQL/PostGIS)
```

Configuration comes from environment variables prefixed `SOLIDARITYNODE_` (see `.env.example`
at the repository root).

Endpoints at this stage: `GET /health`, `GET /health/ready` (checks the database), `GET /version`.
The `scenarios`, `runs`, `results` and `requests` routers are placeholders. Long-running work
goes through `solidaritynode_backend.jobs`, never inside a request handler.

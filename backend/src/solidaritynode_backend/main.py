"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import solidaritynode_backend
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.jobs import InProcessJobRunner
from solidaritynode_backend.routers import health, requests, results, runs, scenarios

__all__ = ["app", "create_app"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Settings to use; defaults to the environment.

    Returns:
        The configured FastAPI app. ``app.state.jobs`` holds the job runner.
    """
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.jobs = InProcessJobRunner()
        try:
            yield
        finally:
            app.state.jobs.shutdown(wait=False)

    app = FastAPI(
        title="SolidarityNode API",
        version=solidaritynode_backend.__version__,
        summary="Spatial probabilistic framework for social service networks (early research).",
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    for module in (health, scenarios, runs, results, requests):
        app.include_router(module.router)
    return app


app = create_app()

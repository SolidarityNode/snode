"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import solidaritynode_backend
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.routers import auth, data, health, requests, runs, scenarios, users

__all__ = ["app", "create_app"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Settings to use; defaults to the environment.

    Returns:
        The configured FastAPI app. Runs execute in the separate worker process
        (:mod:`solidaritynode_backend.worker`), never in a request handler.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title="SolidarityNode API",
        version=solidaritynode_backend.__version__,
        summary="Spatial probabilistic framework for social service networks (early research).",
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        allow_credentials=True,
    )
    for module in (health, auth, users, data, scenarios, runs, requests):
        app.include_router(module.router)
    return app


app = create_app()

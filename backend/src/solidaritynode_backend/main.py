"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import solidaritynode_backend
from solidaritynode_backend.config import DeploymentMode, Settings, get_settings
from solidaritynode_backend.db import get_engine
from solidaritynode_backend.routers import (
    auth,
    data,
    health,
    hub,
    requests,
    runs,
    scenarios,
    users,
)
from solidaritynode_backend.services.installation import check_role

COMMON_ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    auth.router,
    users.router,
    data.router,
    scenarios.router,
    runs.router,
)
ROLE_ROUTERS: dict[DeploymentMode, tuple[APIRouter, ...]] = {
    # Tickets exist only in municipal installations; hub features only in the hub (ADR 0012).
    "municipality": (requests.router,),
    "hub": (hub.router,),
}

__all__ = ["COMMON_ROUTERS", "ROLE_ROUTERS", "app", "create_app"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Settings to use; defaults to the environment.

    Returns:
        The configured FastAPI app with the routers of ``settings.deployment_mode`` only. On start
        it refuses to run if the database was initialised for the other role (ADR 0012). Runs
        execute in the separate worker process (:mod:`solidaritynode_backend.worker`), never in
        a request handler.
    """
    settings = settings or get_settings()
    mode = settings.deployment_mode

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Refuse to start when DEPLOYMENT_MODE differs from the role stored in the database.
        check_role(get_engine(), mode)
        yield

    app = FastAPI(
        lifespan=lifespan,
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
    # Only this role's routers are mounted: the other role's paths do not exist (404).
    for router in (*COMMON_ROUTERS, *ROLE_ROUTERS[mode]):
        app.include_router(router)
    return app


app = create_app()

"""Health and version endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

import solidaritynode_core
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Engine

import solidaritynode_backend
from solidaritynode_backend.db import check_database, get_engine

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """Liveness or readiness status."""

    status: Literal["ok"]


class Version(BaseModel):
    """Versions of the running service and of the core library."""

    name: str
    version: str
    core_version: str


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness: the process is up. Does not touch the database."""
    return Health(status="ok")


@router.get(
    "/health/ready",
    response_model=Health,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Database unreachable"}},
)
def ready(engine: Annotated[Engine, Depends(get_engine)]) -> Health:
    """Readiness: the database answers ``SELECT 1``."""
    if not check_database(engine):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")
    return Health(status="ok")


@router.get("/version", response_model=Version)
def version() -> Version:
    """Return backend and core versions."""
    return Version(
        name="solidaritynode-backend",
        version=solidaritynode_backend.__version__,
        core_version=solidaritynode_core.__version__,
    )

"""ORM mappings of the platform tables (migration 0003).

Geometry columns are not mapped: they are read and written with PostGIS SQL in
:mod:`solidaritynode_backend.packages` and :mod:`solidaritynode_backend.routers.data`.
Bulk feature and result rows use SQL as well; the ORM covers the records the API edits.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from solidaritynode_backend.db import Base

__all__ = [
    "DataVersion",
    "Job",
    "Run",
    "Scenario",
    "ScenarioVersion",
    "Session",
    "User",
]

_JSON = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    """Local account (ADR 0015): ``admin``, ``analyst`` or ``viewer``."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    """Login session; only the SHA-256 of the token is stored."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataVersion(Base):
    """One imported data package version (ADR 0013)."""

    __tablename__ = "data_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)
    created: Mapped[date] = mapped_column(Date)
    srid: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any]] = mapped_column(_JSON)
    manifest_sha256: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Scenario(Base):
    """A scenario with an owner and visibility (ADR 0016); its content lives in versions."""

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    visibility: Mapped[str] = mapped_column(String)
    is_baseline: Mapped[bool] = mapped_column(default=False)
    latest_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScenarioVersion(Base):
    """Immutable version of a scenario: name, description and the JSON overlay."""

    __tablename__ = "scenario_versions"

    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    schema_version: Mapped[str] = mapped_column(Text)
    body: Mapped[dict[str, Any]] = mapped_column(_JSON)
    data_version_id: Mapped[int] = mapped_column(ForeignKey("data_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Job(Base):
    """A background job in the PostgreSQL queue (ADR 0006)."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON)
    status: Mapped[str] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    worker: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(Base):
    """Immutable record of one execution (ADR 0017); lifecycle lives in its job."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id"))
    scenario_version: Mapped[int] = mapped_column(Integer)
    data_version_id: Mapped[int] = mapped_column(ForeignKey("data_versions.id"))
    package_id: Mapped[str] = mapped_column(Text)
    package_version: Mapped[str] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text)
    seed: Mapped[int] = mapped_column(BigInteger)
    config: Mapped[dict[str, Any]] = mapped_column(_JSON)
    input_hash: Mapped[str] = mapped_column(Text)
    is_baseline: Mapped[bool] = mapped_column(default=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    indicators: Mapped[list[dict[str, Any]] | None] = mapped_column(_JSON)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(_JSON)
    samples_path: Mapped[str | None] = mapped_column(Text)
    samples_sha256: Mapped[str | None] = mapped_column(Text)
    seed_source: Mapped[str] = mapped_column(Text, default="given")
    environment: Mapped[dict[str, Any] | None] = mapped_column(_JSON)
    reuse_refused: Mapped[str | None] = mapped_column(Text)
    samples_estimate_bytes: Mapped[int | None] = mapped_column(BigInteger)
    samples_limit_bytes: Mapped[int | None] = mapped_column(BigInteger)

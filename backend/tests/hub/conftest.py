"""Hub test fixtures: one hub database for the session (``DEPLOYMENT_MODE=hub``).

The database is created on the same PostGIS server as the municipal test database, migrated with
``DEPLOYMENT_MODE=hub`` (so migration 0011 creates the hub tables) and dropped at the end. Each
test starts from empty tables; the hub id sequences restart so ids are predictable in tests (in
a real hub they never go backwards).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from tests.conftest import BACKEND, PASSWORDS, REPO

HUB_DEMO = REPO / "data" / "synthetic" / "demo" / "hub"
SOURCES = HUB_DEMO / "sources"
IMPORTS = HUB_DEMO / "imports"
HUB_TABLES = (
    "hub_packages, hub_study_areas, hub_changeset_items, hub_changesets, "
    "hub_processing_records, hub_onboarding_events, hub_onboarding, hub_features, hub_sources, "
    "jobs, sessions, users, login_throttle"
)


@pytest.fixture(scope="session")
def hub_url(database_url: str) -> Iterator[str]:
    from alembic import command
    from alembic.config import Config

    from solidaritynode_backend.config import get_settings

    server = make_url(database_url)
    name = f"sn_hubtest_{uuid.uuid4().hex[:10]}"
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = server.set(database=name).render_as_string(hide_password=False)
    saved = {k: os.environ.get(k) for k in ("SOLIDARITYNODE_DATABASE_URL", "DEPLOYMENT_MODE")}
    os.environ.update({"SOLIDARITYNODE_DATABASE_URL": url, "DEPLOYMENT_MODE": "hub"})
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(cfg, "head")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def _hub_engine(hub_url: str) -> Iterator[Engine]:
    engine = create_engine(hub_url)
    yield engine
    engine.dispose()


@pytest.fixture
def hub_engine(_hub_engine: Engine) -> Engine:
    with _hub_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {HUB_TABLES} RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE hub_facility_id_seq RESTART"))
        conn.execute(text("ALTER SEQUENCE hub_feature_id_seq RESTART"))
    return _hub_engine


@pytest.fixture
def hub_settings(hub_engine: Engine, hub_url: str, tmp_path: Path) -> Any:
    from solidaritynode_backend.config import Settings

    return Settings(
        deployment_mode="hub",
        database_url=hub_url,
        results_dir=tmp_path / "results",
        hub_storage_dir=tmp_path / "hub",
        git_commit="test-commit",
        basemap="blank",
        login_delay_base_s=0,
        diagnostic_step_delay_s=0,
    )


@pytest.fixture
def hub_db(hub_engine: Engine) -> Iterator[Session]:
    with Session(hub_engine) as session:
        yield session


@pytest.fixture
def hub_app(hub_settings: Any, hub_engine: Engine) -> Any:
    from solidaritynode_backend.config import get_settings
    from solidaritynode_backend.db import get_engine, get_session
    from solidaritynode_backend.main import create_app

    application = create_app(hub_settings)

    def session() -> Iterator[Session]:
        with Session(hub_engine, expire_on_commit=False) as s:
            yield s

    application.dependency_overrides[get_settings] = lambda: hub_settings
    application.dependency_overrides[get_session] = session
    application.dependency_overrides[get_engine] = lambda: hub_engine
    return application


@pytest.fixture
def hub_worker(hub_engine: Engine, hub_settings: Any) -> Any:
    from solidaritynode_backend.worker import build_worker

    return build_worker(hub_settings, hub_engine)


@pytest.fixture
def hub_users(hub_db: Session) -> dict[str, int]:
    from solidaritynode_backend.auth import create_user

    ids = {role: create_user(hub_db, role, pw, role).id for role, pw in PASSWORDS.items()}  # type: ignore[arg-type]
    hub_db.commit()
    return ids


def hub_login(app: Any, username: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/auth/login", json={"username": username, "password": PASSWORDS[username]}
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def hub_admin(hub_app: Any, hub_users: dict[str, int]) -> TestClient:
    return hub_login(hub_app, "admin")


@pytest.fixture
def demo_sources(hub_db: Session, hub_settings: Any) -> None:
    from solidaritynode_backend.services.hub.sources import register_from_metadata

    register_from_metadata(hub_db, hub_settings, SOURCES, None)
    hub_db.commit()


def onboard(db: Session, settings: Any, worker: Any, municipality: str) -> dict[str, Any]:
    """Run the base step for ``municipality`` and return its processing record."""
    from solidaritynode_backend.jobs import PostgresJobRunner
    from solidaritynode_backend.services.hub.base import start_base

    record_id, _ = start_base(db, settings, PostgresJobRunner(db), municipality, None)
    db.commit()
    worker.run_until_idle()
    row = (
        db.execute(text("SELECT * FROM hub_processing_records WHERE id = :id"), {"id": record_id})
        .mappings()
        .one()
    )
    db.commit()
    return dict(row)

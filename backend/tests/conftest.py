"""Test configuration: ``APP_ENV=test`` and a throw-away PostGIS database.

Database tests create a fresh database on the server given by ``SOLIDARITYNODE_TEST_DATABASE_URL``
(default: the compose ``db`` service on 127.0.0.1:5432 with the development credentials), apply
every Alembic migration, and drop it at the end. ``make test-backend`` starts no containers: run
``make test-db`` (or ``make up``) first. CI uses a PostGIS service container.
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PACKAGES = REPO / "data" / "synthetic" / "packages"
DEFAULT_SERVER = "postgresql+psycopg://solidaritynode:change-me@127.0.0.1:5432/solidaritynode"
TABLES = (
    "run_tables, run_results, runs, jobs, scenario_versions, scenarios, data_warnings, "
    "data_coverage, data_records, data_features, data_versions, sessions, users, login_throttle"
)
PASSWORDS = {"admin": "admin-pass-123", "analyst": "analyst-pass-123", "viewer": "viewer-pass-123"}


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    server = make_url(os.environ.get("SOLIDARITYNODE_TEST_DATABASE_URL", DEFAULT_SERVER))
    name = f"sn_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # pragma: no cover - environment problem, explained to the developer
        pytest.fail(
            f"PostGIS for tests is not reachable at {server.render_as_string(hide_password=True)}"
            f" ({type(exc).__name__}). Start it with `make test-db` (or `make up`), or set "
            "SOLIDARITYNODE_TEST_DATABASE_URL.",
            pytrace=False,
        )
    url = server.set(database=name).render_as_string(hide_password=False)
    previous = os.environ.get("SOLIDARITYNODE_DATABASE_URL")
    os.environ["SOLIDARITYNODE_DATABASE_URL"] = url
    from alembic import command
    from alembic.config import Config

    from solidaritynode_backend.config import get_settings
    from solidaritynode_backend.db import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")
    yield url
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()
    if previous is None:
        os.environ.pop("SOLIDARITYNODE_DATABASE_URL", None)
    else:
        os.environ["SOLIDARITYNODE_DATABASE_URL"] = previous
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def engine(database_url: str) -> Engine:
    from solidaritynode_backend.db import get_engine

    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    return eng


@pytest.fixture
def settings(engine: Engine, tmp_path: Path) -> Any:
    from solidaritynode_backend.config import Settings

    return Settings(
        results_dir=tmp_path / "results",
        packages_dir=PACKAGES,
        diagnostic_step_delay_s=0,
        git_commit="test-commit",
        basemap="blank",
        login_delay_base_s=0,  # throttling tests set their own delays
    )


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@pytest.fixture
def app(settings: Any) -> Any:
    from solidaritynode_backend.config import get_settings
    from solidaritynode_backend.main import create_app

    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
def worker(engine: Engine, settings: Any) -> Any:
    from solidaritynode_backend.worker import build_worker

    return build_worker(settings, engine)


@pytest.fixture
def users(db: Session) -> dict[str, int]:
    from solidaritynode_backend.auth import create_user

    ids = {}
    for role, password in PASSWORDS.items():
        ids[role] = create_user(db, role, password, role).id  # type: ignore[arg-type]
    ids["analyst2"] = create_user(db, "analyst2", PASSWORDS["analyst"], "analyst").id
    db.commit()
    return ids


def login(app: Any, username: str) -> TestClient:
    """Return a client logged in as ``username`` (users fixture)."""
    client = TestClient(app)
    password = PASSWORDS.get(username, PASSWORDS["analyst"])
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def as_admin(app: Any, users: dict[str, int]) -> TestClient:
    return login(app, "admin")


@pytest.fixture
def as_analyst(app: Any, users: dict[str, int]) -> TestClient:
    return login(app, "analyst")


@pytest.fixture
def as_viewer(app: Any, users: dict[str, int]) -> TestClient:
    return login(app, "viewer")


def import_version(client: TestClient, version: str) -> dict[str, Any]:
    """Preview and import ``demo-<version>`` through the API; return the import outcome."""
    preview = client.post("/packages/preview", json={"name": f"demo-{version}"})
    assert preview.status_code == 200, preview.text
    response = client.post("/packages/import", json={"name": f"demo-{version}"})
    assert response.status_code == 200, response.text
    return dict(response.json())


CLOSE_E02 = {
    "name": "Close E02",
    "description": "Synthetic test scenario",
    "visibility": "shared",
    "body": {
        "closed_edges": {"edge_ids": ["E02"], "modes": ["walk", "car"]},
        "rationing": "uniform",
    },
}

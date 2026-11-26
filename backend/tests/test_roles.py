"""Deployment role lock and role separation (ADR 0012)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from solidaritynode_backend.services.installation import (
    HUB_ONLY_TABLES,
    MUNICIPALITY_ONLY_TABLES,
    RoleMismatchError,
    check_role,
    stored_role,
)
from tests.conftest import BACKEND, login

ROLE_PATHS = {"municipality": "/requests/status", "hub": "/hub/status"}


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }


@pytest.fixture
def hub_database(database_url: str) -> Iterator[Engine]:
    """A fresh database migrated with DEPLOYMENT_MODE=hub (dropped afterwards)."""
    from alembic import command
    from alembic.config import Config

    from solidaritynode_backend.config import get_settings

    server = make_url(database_url)
    name = f"sn_hub_{uuid.uuid4().hex[:10]}"
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
    hub = create_engine(url)
    yield hub
    hub.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def test_role_is_stored_at_first_initialisation_and_locks_the_database(
    engine: Engine, settings: Any
) -> None:
    from solidaritynode_backend.main import create_app

    with engine.connect() as conn:
        assert stored_role(conn) == "municipality"  # recorded by migration 0007
    assert check_role(engine, "municipality") == "municipality"
    with pytest.raises(RoleMismatchError, match="initialised for a 'municipality' installation"):
        check_role(engine, "hub")
    hub_app = create_app(settings.model_copy(update={"deployment_mode": "hub"}))
    with (
        pytest.raises(RoleMismatchError, match="Refusing to start"),
        TestClient(hub_app),  # startup runs the check
    ):
        pass
    with TestClient(create_app(settings)) as client:  # the matching role starts
        assert client.get("/health").status_code == 200


def test_a_database_without_a_recorded_role_records_the_first_one(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM installation"))
    try:
        assert check_role(engine, "municipality") == "municipality"
        with engine.connect() as conn:
            assert stored_role(conn) == "municipality"
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO installation (deployment_mode) VALUES ('municipality') "
                    "ON CONFLICT (id) DO NOTHING"
                )
            )


@pytest.mark.parametrize("mode", ["municipality", "hub"])
def test_the_other_roles_routes_do_not_exist(mode: str, settings: Any, users: Any) -> None:
    from solidaritynode_backend.main import create_app

    app = create_app(settings.model_copy(update={"deployment_mode": mode}))
    client = login(app, "analyst")
    other = "hub" if mode == "municipality" else "municipality"
    own = client.get(ROLE_PATHS[mode])
    assert own.status_code == 200
    assert own.json()["role"] == mode
    assert own.json()["implemented"] is (mode == "hub")  # tickets wait for ADR 0010
    assert client.get(ROLE_PATHS[other]).status_code == 404
    paths = set(app.openapi()["paths"])
    prefix = ROLE_PATHS[other].rsplit("/", 1)[0]
    assert not any(p == prefix or p.startswith(prefix + "/") for p in paths), (
        "other role's routes are not mounted"
    )
    assert any(p.startswith(ROLE_PATHS[mode].rsplit("/", 1)[0]) for p in paths)


def test_ticket_tables_never_exist_in_the_hub(engine: Engine, hub_database: Engine) -> None:
    with hub_database.connect() as conn:
        assert stored_role(conn) == "hub"
    hub_tables, municipal_tables = _tables(hub_database), _tables(engine)
    assert not hub_tables & set(MUNICIPALITY_ONLY_TABLES)
    assert not municipal_tables & set(HUB_ONLY_TABLES)
    assert not any("ticket" in t or "request" in t for t in hub_tables)
    with pytest.raises(RoleMismatchError):
        check_role(hub_database, "municipality")

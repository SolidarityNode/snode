from __future__ import annotations

from collections.abc import Iterator

import pytest
import solidaritynode_core
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from solidaritynode_backend.db import get_engine
from solidaritynode_backend.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version(client: TestClient) -> None:
    body = client.get("/version").json()
    assert body["name"] == "solidaritynode-backend"
    assert body["core_version"] == solidaritynode_core.__version__


def test_ready_reports_database_state(client: TestClient) -> None:
    app = client.app
    ok_engine = create_engine("sqlite://", poolclass=StaticPool)
    app.dependency_overrides[get_engine] = lambda: ok_engine  # type: ignore[attr-defined]
    assert client.get("/health/ready").status_code == 200

    bad_engine = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    app.dependency_overrides[get_engine] = lambda: bad_engine  # type: ignore[attr-defined]
    assert client.get("/health/ready").status_code == 503


def test_openapi_lists_health_and_licence(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    assert {"/health", "/health/ready", "/version"} <= set(openapi["paths"])
    assert openapi["info"]["license"]["identifier"] == "AGPL-3.0-or-later"

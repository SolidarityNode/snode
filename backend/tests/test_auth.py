"""Local accounts, sessions and role permissions (ADR 0015)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from solidaritynode_backend.auth import hash_password, verify_password
from solidaritynode_backend.cli import seed_demo_users
from tests.conftest import CLOSE_E02, import_version, login


def test_passwords_are_hashed_with_argon2() -> None:
    hashed = hash_password("a-long-password")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "a-long-password")
    assert not verify_password(hashed, "wrong")
    with pytest.raises(ValueError, match="at least 8"):
        hash_password("short")


def test_login_logout_and_me(app, users) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(app)
    assert client.get("/auth/me").status_code == 401
    bad = client.post("/auth/login", json={"username": "analyst", "password": "nope-nope"})
    assert bad.status_code == 401
    ok = client.post("/auth/login", json={"username": "analyst", "password": "analyst-pass-123"})
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert client.get("/auth/me").json()["role"] == "analyst"
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_every_data_endpoint_requires_login(app, users) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(app)
    for path in ("/scenarios", "/runs", "/data-versions", "/users", "/packages/available"):
        assert client.get(path).status_code == 401, path
    assert client.get("/config").status_code == 200


def test_role_permissions(app, users, as_admin, as_analyst, as_viewer) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    # Users and packages: admin only.
    assert as_admin.get("/users").status_code == 200
    assert as_analyst.get("/users").status_code == 403
    assert as_viewer.get("/packages/available").status_code == 403
    assert as_analyst.post("/packages/import", json={"name": "demo-1.1.0"}).status_code == 403
    # Viewers cannot create scenarios; analysts can.
    assert as_viewer.post("/scenarios", json=CLOSE_E02).status_code == 403
    shared = as_analyst.post("/scenarios", json=CLOSE_E02).json()
    private = as_analyst.post("/scenarios", json={**CLOSE_E02, "visibility": "private"}).json()
    viewer_ids = {s["id"] for s in as_viewer.get("/scenarios").json()}
    assert shared["id"] in viewer_ids
    assert private["id"] not in viewer_ids
    assert as_viewer.get(f"/scenarios/{private['id']}").status_code == 404
    # Another analyst sees shared, cannot edit, run or delete it.
    other = login(app, "analyst2")
    assert other.get(f"/scenarios/{shared['id']}").json()["can_edit"] is False
    assert other.put(f"/scenarios/{shared['id']}", json=CLOSE_E02).status_code == 403
    assert other.post("/runs", json={"scenario_id": shared["id"]}).status_code == 403
    assert other.delete(f"/scenarios/{shared['id']}").status_code == 403
    assert as_viewer.post("/runs", json={"scenario_id": shared["id"]}).status_code == 403
    # Admin sees and may edit everything.
    assert as_admin.get(f"/scenarios/{private['id']}").json()["can_edit"] is True


def test_admin_manages_users(as_admin, app) -> None:  # type: ignore[no-untyped-def]
    created = as_admin.post(
        "/users", json={"username": "new-viewer", "password": "viewer-pass-9", "role": "viewer"}
    )
    assert created.status_code == 201
    uid = created.json()["id"]
    assert (
        as_admin.post(
            "/users", json={"username": "new-viewer", "password": "viewer-pass-9", "role": "viewer"}
        ).status_code
        == 409
    )
    client = TestClient(app)
    client.post("/auth/login", json={"username": "new-viewer", "password": "viewer-pass-9"})
    assert client.get("/auth/me").status_code == 200
    assert as_admin.patch(f"/users/{uid}", json={"active": False}).json()["active"] is False
    assert client.get("/auth/me").status_code == 401  # sessions of disabled users end
    me = as_admin.get("/auth/me").json()["id"]
    assert as_admin.patch(f"/users/{me}", json={"role": "viewer"}).status_code == 409


def test_demo_users_only_in_development(settings, db) -> None:  # type: ignore[no-untyped-def]
    assert settings.app_env == "test"
    assert seed_demo_users(settings) == 1

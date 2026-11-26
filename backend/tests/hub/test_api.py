"""Hub API: the whole flow over HTTP and the permissions of every hub endpoint."""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.hub.conftest import IMPORTS, SOURCES, hub_login

ROLES = ("viewer", "analyst", "admin")
# Every hub endpoint with the lowest role allowed. A new endpoint must be added here.
PERMISSIONS: dict[tuple[str, str], str] = {
    ("GET", "/hub/status"): "viewer",
    ("GET", "/hub/sources"): "viewer",
    ("POST", "/hub/sources"): "admin",
    ("GET", "/hub/coverage"): "viewer",
    ("GET", "/hub/onboarding/{municipality_id}"): "viewer",
    ("POST", "/hub/onboarding/{municipality_id}/base"): "admin",
    ("POST", "/hub/onboarding/{municipality_id}/status"): "admin",
    ("GET", "/hub/records/{record_id}"): "viewer",
    ("GET", "/hub/jobs/{job_id}"): "viewer",
    ("POST", "/hub/jobs/{job_id}/cancel"): "admin",
    ("GET", "/hub/facilities/template"): "viewer",
    ("GET", "/hub/facilities/export"): "viewer",
    ("GET", "/hub/facilities"): "viewer",
    ("GET", "/hub/facilities/{facility_id}/history"): "viewer",
    ("POST", "/hub/facility-imports"): "analyst",
    ("POST", "/hub/facilities/edits"): "analyst",
    ("GET", "/hub/changesets"): "viewer",
    ("GET", "/hub/changesets/{changeset_id}"): "viewer",
    ("GET", "/hub/changesets/{changeset_id}/report"): "viewer",
    ("POST", "/hub/changesets/{changeset_id}/approve"): "admin",
    ("POST", "/hub/changesets/{changeset_id}/reject"): "admin",
    ("GET", "/hub/study-areas"): "viewer",
    ("POST", "/hub/study-areas"): "admin",
    ("POST", "/hub/study-areas/{study_area_id}/publish"): "admin",
    ("GET", "/hub/study-areas/{study_area_id}/packages/{version}/download"): "viewer",
    ("POST", "/hub/changesets/{changeset_id}/review"): "admin",
    ("POST", "/hub/submission-files"): "admin",
    ("GET", "/hub/installations"): "admin",
    ("POST", "/hub/installations"): "admin",
    ("POST", "/hub/installations/{installation_id}/token"): "admin",
    ("POST", "/hub/installations/{installation_id}/revoke"): "admin",
}
# The installation API takes only installation tokens, never a session (any role: 401).
TOKEN_ONLY: set[tuple[str, str]] = {
    ("GET", "/hub/installation/me"),
    ("POST", "/hub/installation/submissions"),
    ("GET", "/hub/installation/submissions"),
    ("POST", "/hub/installation/submissions/{submission_id}/withdraw"),
    ("GET", "/hub/installation/packages/{version}/download"),
}
SAMPLE = {
    "municipality_id": "M-A",
    "record_id": "1",
    "job_id": "00000000-0000-0000-0000-000000000000",
    "facility_id": "HF-000001",
    "changeset_id": "1",
    "study_area_id": "study-area-a",
    "version": "1.0.0",
    "installation_id": "00000000-0000-0000-0000-000000000000",
    "submission_id": "00000000-0000-0000-0000-000000000000",
}


def _path(template: str) -> str:
    for key, value in SAMPLE.items():
        template = template.replace("{" + key + "}", value)
    return template


def test_every_hub_endpoint_is_in_the_permission_table(hub_app: Any) -> None:
    routes = {
        (method.upper(), path)
        for path, operations in hub_app.openapi()["paths"].items()
        if path.startswith("/hub")
        for method in operations
    }
    assert routes == set(PERMISSIONS) | TOKEN_ONLY


@pytest.mark.parametrize(("method", "path"), sorted(TOKEN_ONLY))
def test_installation_api_refuses_sessions(
    hub_app: Any, hub_users: Any, method: str, path: str
) -> None:
    for role in (None, *ROLES):
        client = TestClient(hub_app) if role is None else hub_login(hub_app, role)
        response = client.request(method, _path(path), json={}, params={"ids": []})
        assert response.status_code == 401, (role, response.text)


@pytest.mark.parametrize(("method", "path"), sorted(PERMISSIONS))
def test_permissions_per_role(hub_app: Any, hub_users: Any, method: str, path: str) -> None:
    anonymous = TestClient(hub_app).request(method, _path(path))
    assert anonymous.status_code == 401, anonymous.text
    lowest = ROLES.index(PERMISSIONS[(method, path)])
    for i, role in enumerate(ROLES):
        response = hub_login(hub_app, role).request(method, _path(path), json={})
        if i < lowest:
            assert response.status_code == 403, (role, response.text)
        else:
            assert response.status_code not in (401, 403), (role, response.text)


def _register(client: TestClient) -> None:
    import json

    for entry in json.loads((SOURCES / "sources.json").read_text()):
        params = {k: v for k, v in entry.items() if k != "file"}
        response = client.post(
            "/hub/sources",
            params={**params, "file_name": entry["file"]},
            content=(SOURCES / entry["file"]).read_bytes(),
        )
        assert response.status_code == 201, response.text


def test_whole_flow_over_http(hub_app: Any, hub_users: Any, hub_worker: Any) -> None:
    admin = hub_login(hub_app, "admin")
    analyst = hub_login(hub_app, "analyst")
    _register(admin)
    sources = admin.get("/hub/sources").json()
    assert len(sources) == 6
    assert all(len(s["sha256"]) == 64 for s in sources)
    again = admin.post(
        "/hub/sources",
        params={
            k: v
            for k, v in sources[0].items()
            if k
            in (
                "name",
                "layer_type",
                "version",
                "licence",
                "attribution",
                "processing_note",
                "coverage",
                "quality",
            )
        }
        | {"file_name": sources[0]["file_name"]},
        content=(SOURCES / sources[0]["file_name"]).read_bytes(),
    )
    assert again.status_code == 200
    assert again.json()["created"] is False

    matrix = admin.get("/hub/coverage").json()
    assert [r["municipality_id"] for r in matrix] == ["M-A", "M-B", "M-C", "M-D"]
    assert all(r["layers"]["boundaries"]["status"] == "missing" for r in matrix)

    started = admin.post("/hub/onboarding/M-A/base").json()
    assert admin.get(f"/hub/jobs/{started['job_id']}").json()["status"] == "queued"
    hub_worker.run_until_idle()
    detail = admin.get("/hub/onboarding/M-A").json()
    assert detail["status"] == "base_ready"
    assert detail["job"]["status"] == "succeeded"
    assert detail["records"][0]["status"] == "succeeded"
    assert [e["to_status"] for e in detail["events"]] == ["base_ready"]
    onboarded = admin.get("/hub/coverage", params={"onboarded": "true"}).json()
    assert [r["municipality_id"] for r in onboarded] == ["M-A"]
    a = onboarded[0]["layers"]
    assert (a["boundaries"]["status"], a["facilities"]["status"], a["transit"]["status"]) == (
        "open_data",
        "missing",
        "missing",
    )
    assert a["network"]["version"] == "2026-11"

    upload = analyst.post(
        "/hub/facility-imports",
        params={
            "municipality": "M-A",
            "file_name": "facilities-M-A-personal.csv",
            "source": "Synthetic municipal register",
        },
        content=(IMPORTS / "facilities-M-A-personal.csv").read_bytes(),
    )
    assert upload.status_code == 201, upload.text
    cs = upload.json()
    assert cs["status"] == "pending"
    assert cs["report"]["summary"] == {"add": 3, "update": 0, "close": 0}
    assert analyst.post(f"/hub/changesets/{cs['id']}/approve", json={}).status_code == 403
    approved = admin.post(f"/hub/changesets/{cs['id']}/approve", json={"comment": "ok"})
    assert approved.status_code == 200, approved.text
    assert [i["facility_id"] for i in approved.json()["items"]] == [
        "HF-000001",
        "HF-000002",
        "HF-000003",
    ]
    report = admin.get(f"/hub/changesets/{cs['id']}/report", params={"format": "csv"})
    assert "contact_person" in report.text
    history = admin.get("/hub/facilities/HF-000001/history").json()
    assert history[0]["action"] == "add"

    template = admin.get("/hub/facilities/template", params={"format": "xlsx"})
    assert template.headers["content-type"].startswith("application/vnd.openxmlformats")

    area = admin.post(
        "/hub/study-areas",
        json={"id": "study-area-a", "name": "Study area A", "core_municipalities": ["M-A"]},
    )
    assert area.status_code == 201, area.text
    assert area.json()["buffer_municipalities"] == ["M-B", "M-C"]
    published = admin.post("/hub/study-areas/study-area-a/publish", json={})
    assert published.status_code == 202, published.text
    assert published.json()["version"] == "1.0.0"
    hub_worker.run_until_idle()
    areas = admin.get("/hub/study-areas").json()
    assert areas[0]["packages"][0]["status"] == "published"
    download = admin.get("/hub/study-areas/study-area-a/packages/1.0.0/download")
    assert download.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(download.content)).namelist()
    assert {"manifest.json", "layers.gpkg", "tables/population.csv"} <= set(names)
    again_publish = admin.post("/hub/study-areas/study-area-a/publish", json={})
    assert again_publish.status_code == 409
    assert "nothing to publish" in again_publish.json()["detail"]


def test_municipal_installation_has_no_hub_routes(app: Any, users: Any) -> None:
    from tests.conftest import login

    client = login(app, "admin")
    assert client.get("/hub/sources").status_code == 404
    config = client.get("/config").json()
    assert config["docs_url"] == "https://solidaritynode.github.io/snode/0.1/"

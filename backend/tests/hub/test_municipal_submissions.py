"""Municipal side of submissions, against a real hub app in the same test (ADR 0014 Part A).

The municipal worker's transport is replaced by one that calls the hub app directly, so every
request it sends can be inspected, and the hub can be made unreachable.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import PASSWORDS
from tests.hub.conftest import IMPORTS, hub_login, onboard
from tests.hub.test_publish import _area, _import_facilities, _package_dir, _publish

HUB_URL = "http://hub.test/api"


class FakeHub:
    """Transport to the hub app; records requests and can drop the connection."""

    def __init__(self, app: Any) -> None:
        self.client = TestClient(app)
        self.requests: list[tuple[str, str, bytes | None]] = []
        self.down = False
        self.lose_reply = False

    def __call__(
        self, method: str, url: str, headers: Any, body: bytes | None
    ) -> tuple[int, bytes]:
        from solidaritynode_backend.services.submissions import HubUnreachableError

        if self.down:
            raise HubUnreachableError("connection refused")
        path = url.removeprefix(HUB_URL)
        self.requests.append((method, path, body))
        response = self.client.request(
            method, path, content=body, headers={k: v for k, v in headers.items()}
        )
        if self.lose_reply and method == "POST":
            raise HubUnreachableError("connection reset after sending")
        return response.status_code, response.content

    def bodies(self, path: str) -> list[dict[str, Any]]:
        return [json.loads(b) for m, p, b in self.requests if m == "POST" and p == path and b]


@pytest.fixture
def linked(
    hub_db: Session,
    hub_settings: Any,
    hub_worker: Any,
    demo_sources: None,
    hub_users: Any,
    hub_app: Any,
    db: Session,
    settings: Any,
    users: Any,
    engine: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """A hub that published study-area-a 1.0.0, and a municipal installation linked to it."""
    from solidaritynode_backend.config import get_settings
    from solidaritynode_backend.main import create_app
    from solidaritynode_backend.services import submissions
    from solidaritynode_backend.services.hub.installations import register_installation
    from solidaritynode_backend.services.packages import import_package, read_package
    from solidaritynode_backend.worker import build_worker

    onboard(hub_db, hub_settings, hub_worker, "M-A")
    _import_facilities(hub_db, hub_settings, "M-A", "facilities-M-A.csv")
    _area(hub_db, hub_settings, "study-area-a", "M-A")
    package = _publish(hub_db, hub_settings, hub_worker, "study-area-a")
    _, token = register_installation(hub_db, "Municipality A installation", "study-area-a", 1)
    hub_db.commit()
    import_package(db, settings, read_package(_package_dir(hub_settings, package)), None)
    db.execute(
        text(
            "UPDATE hub_link SET study_area_id = NULL, installation_id = NULL, "
            "installation_name = NULL, packages = '[]', last_error = NULL, last_sync_at = NULL, "
            "last_contact_at = NULL"
        )
    )
    db.commit()
    municipal = settings.model_copy(
        update={"hub_url": HUB_URL, "hub_token": type(settings.hub_token)(token)}
    )
    fake = FakeHub(hub_app)
    monkeypatch.setattr(submissions, "TRANSPORT", fake)
    app = create_app(municipal)
    app.dependency_overrides[get_settings] = lambda: municipal
    return {
        "app": app,
        "settings": municipal,
        "worker": build_worker(municipal, engine),
        "fake": fake,
        "hub_app": hub_app,
        "token": token,
    }


def _login(app: Any, username: str) -> TestClient:
    client = TestClient(app)
    password = PASSWORDS.get(username, PASSWORDS["analyst"])
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client


def _upload(client: TestClient, file: str, **params: Any) -> dict[str, Any]:
    response = client.post(
        "/submissions/upload",
        params={"municipality": "M-A", "file_name": file, **params},
        content=(IMPORTS / file).read_bytes(),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _sync(linked: dict[str, Any]) -> None:
    from solidaritynode_backend.services.submissions import SYNC_JOB_KIND

    with Session(linked["worker"].engine) as db:
        db.execute(text("UPDATE submissions SET next_attempt_at = now() WHERE status = 'sent'"))
        busy = db.execute(
            text("SELECT 1 FROM jobs WHERE kind = :k AND status = 'queued'"), {"k": SYNC_JOB_KIND}
        ).first()
        if not busy:
            from solidaritynode_backend.jobs import PostgresJobRunner

            PostgresJobRunner(db).submit(SYNC_JOB_KIND, {})
        db.commit()
    linked["worker"].run_until_idle()


def test_personal_data_never_leaves_the_installation(linked: dict[str, Any]) -> None:
    analyst = _login(linked["app"], "analyst")
    draft = _upload(analyst, "facilities-M-A-personal.csv")
    codes = [e["code"] for e in draft["report"]["entries"]]
    assert codes.count("hub.import.personal_column") == 2
    assert "hub.import.personal_value" in codes
    assert draft["status"] == "draft"
    assert linked["fake"].requests == []  # nothing sent while checking locally
    sent = analyst.post(f"/submissions/{draft['id']}/send", json={})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    _sync(linked)
    bodies = linked["fake"].bodies("/hub/installation/submissions")
    assert len(bodies) == 1
    raw = json.dumps(bodies[0])
    for personal in ("Maria", "contact_person", "mobile", "6900000000", "6912345678"):
        assert personal not in raw
    assert bodies[0]["submitted_by"].startswith("u-")
    assert "analyst" not in bodies[0]["submitted_by"]
    done = analyst.get(f"/submissions/{draft['id']}").json()
    assert done["status"] == "pending_review"
    assert [e["to_status"] for e in done["events"]] == [
        "draft",
        "sent",
        "received",
        "pending_review",
    ]


def test_hub_unreachable_retries_and_arrives_once(linked: dict[str, Any], hub_db: Session) -> None:
    analyst = _login(linked["app"], "analyst")
    draft = _upload(analyst, "facilities-M-A-update.csv")
    analyst.post(f"/submissions/{draft['id']}/send", json={})
    linked["fake"].down = True
    _sync(linked)
    after = analyst.get(f"/submissions/{draft['id']}").json()
    assert after["status"] == "sent"
    assert after["attempts"] == 1
    assert "could not be reached" in after["last_error"]
    # The hub receives the next try but the reply is lost: still "sent", tried again.
    linked["fake"].down = False
    linked["fake"].lose_reply = True
    _sync(linked)
    assert analyst.get(f"/submissions/{draft['id']}").json()["status"] == "sent"
    linked["fake"].lose_reply = False
    _sync(linked)
    final = analyst.get(f"/submissions/{draft['id']}").json()
    assert final["status"] == "pending_review"
    assert len(linked["fake"].bodies("/hub/installation/submissions")) == 2
    count = hub_db.execute(
        text("SELECT count(*) FROM hub_changesets WHERE submission_uuid = :u"),
        {"u": draft["id"]},
    ).scalar_one()
    assert count == 1  # the resend did not create a duplicate


def test_whole_flow_to_imported(
    linked: dict[str, Any], hub_db: Session, hub_settings: Any, hub_worker: Any
) -> None:
    analyst = _login(linked["app"], "analyst")
    admin = _login(linked["app"], "admin")
    draft = _upload(analyst, "facilities-M-A-update.csv", comment="corrected throughput")
    assert draft["report"]["summary"] == {"add": 1, "update": 1, "close": 0}
    analyst.post(f"/submissions/{draft['id']}/send", json={})
    _sync(linked)
    changeset_id = analyst.get(f"/submissions/{draft['id']}").json()["hub_changeset_id"]
    hub_admin = hub_login(linked["hub_app"], "admin")
    cs = hub_admin.get(f"/hub/changesets/{changeset_id}").json()
    assert cs["source"].startswith("submitted by municipality M-A (installation Municipality A")
    assert (
        hub_admin.post(
            f"/hub/changesets/{changeset_id}/approve", json={"comment": "thanks"}
        ).status_code
        == 200
    )
    _sync(linked)
    approved = analyst.get(f"/submissions/{draft['id']}").json()
    assert approved["status"] == "approved"
    assert approved["hub_comment"] == "thanks"
    assert hub_admin.post("/hub/study-areas/study-area-a/publish", json={}).status_code == 202
    hub_worker.run_until_idle()
    _sync(linked)
    assert analyst.get(f"/submissions/{draft['id']}").json()["published_in"] == "1.1.0"
    link = admin.get("/hub-link").json()
    assert [v["version"] for v in link["new_versions"]] == ["1.1.0"]
    assert link["token_present"] is True
    assert linked["token"] not in json.dumps(link)
    download = admin.post("/hub-link/downloads", json={"version": "1.1.0"}).json()
    linked["worker"].run_until_idle()
    done = admin.get(f"/hub-link/downloads/{download['id']}").json()
    assert done["status"] == "done", done
    preview = admin.get(f"/hub-link/downloads/{download['id']}/preview").json()
    assert preview["version"] == "1.1.0"
    assert preview["layers"]["facilities"]["added"] == ["HF-000004"]
    imported = admin.post("/packages/import", json={"staging_id": done["staging_id"]})
    assert imported.status_code == 200, imported.text
    final = analyst.get(f"/submissions/{draft['id']}").json()
    assert (final["status"], final["imported_in"]) == ("imported", "1.1.0")


def test_withdraw_before_review(linked: dict[str, Any]) -> None:
    analyst = _login(linked["app"], "analyst")
    draft = _upload(analyst, "facilities-M-A-update.csv")
    assert analyst.post(f"/submissions/{draft['id']}/withdraw").json()["status"] == "withdrawn"
    other = _upload(analyst, "facilities-M-A-update.csv")
    analyst.post(f"/submissions/{other['id']}/send", json={})
    _sync(linked)
    asked = analyst.post(f"/submissions/{other['id']}/withdraw").json()
    assert asked["withdraw_requested"] is True
    _sync(linked)
    assert analyst.get(f"/submissions/{other['id']}").json()["status"] == "withdrawn"
    # Another analyst cannot withdraw someone else's submission.
    third = _upload(analyst, "facilities-M-A-update.csv")
    refused = _login(linked["app"], "analyst2").post(f"/submissions/{third['id']}/withdraw")
    assert refused.status_code == 403


def test_conflict_resolution_is_visible_to_the_submitter(
    linked: dict[str, Any], hub_db: Session, hub_settings: Any
) -> None:
    from solidaritynode_backend.services.hub.facilities import approve_changeset, manual_changeset

    edit = manual_changeset(
        hub_db,
        hub_settings,
        "M-A",
        "HF-000002",
        {"notes": "changed by the hub"},
        [],
        False,
        "hub",
        1,
    )
    approve_changeset(hub_db, hub_settings, edit, 1)
    hub_db.commit()
    analyst = _login(linked["app"], "analyst")
    draft = _upload(analyst, "facilities-M-A-update.csv")
    analyst.post(f"/submissions/{draft['id']}/send", json={})
    _sync(linked)
    changeset_id = analyst.get(f"/submissions/{draft['id']}").json()["hub_changeset_id"]
    hub_admin = hub_login(linked["hub_app"], "admin")
    items = hub_admin.get(f"/hub/changesets/{changeset_id}").json()["items"]
    conflicted = [i for i in items if i["conflict"]]
    assert [i["facility_id"] for i in conflicted] == ["HF-000002"]
    assert "notes" in conflicted[0]["conflict"]["fields"]
    hub_admin.post(
        f"/hub/changesets/{changeset_id}/approve",
        json={"resolutions": {str(conflicted[0]["item_no"]): "municipality"}},
    )
    _sync(linked)
    seen = analyst.get(f"/submissions/{draft['id']}").json()
    assert seen["hub_conflicts"][0]["facility_id"] == "HF-000002"
    assert seen["hub_conflicts"][0]["resolution"] == "municipality"


def test_offline_file_matches_the_online_submission(linked: dict[str, Any]) -> None:
    analyst = _login(linked["app"], "analyst")
    _sync(linked)  # one contact gives the installation id for the signature
    online = _upload(analyst, "facilities-M-A-update.csv")
    analyst.post(f"/submissions/{online['id']}/send", json={})
    _sync(linked)
    offline = _upload(analyst, "facilities-M-A-update.csv")
    exported = analyst.get(f"/submissions/{offline['id']}/export")
    assert exported.status_code == 200, exported.text
    assert analyst.get(f"/submissions/{offline['id']}").json()["offline"] is True
    hub_admin = hub_login(linked["hub_app"], "admin")
    uploaded = hub_admin.post("/hub/submission-files", content=exported.content)
    assert uploaded.status_code == 201, uploaded.text
    on_id = analyst.get(f"/submissions/{online['id']}").json()["hub_changeset_id"]
    on = hub_admin.get(f"/hub/changesets/{on_id}").json()

    def strip(cs: dict[str, Any]) -> list[Any]:
        return [(i["action"], i["facility_id"], i["fields"], i["after"]) for i in cs["items"]]

    assert strip(on) == strip(uploaded.json())
    _sync(linked)
    assert analyst.get(f"/submissions/{offline['id']}").json()["status"] == "pending_review"


MUNICIPAL_ENDPOINTS = {
    ("GET", "/submissions"): "analyst",
    ("POST", "/submissions/upload"): "analyst",
    ("POST", "/submissions/edits"): "analyst",
    ("POST", "/submissions/sync"): "analyst",
    ("GET", "/submissions/{submission_id}"): "analyst",
    ("POST", "/submissions/{submission_id}/send"): "analyst",
    ("POST", "/submissions/{submission_id}/withdraw"): "analyst",
    ("GET", "/submissions/{submission_id}/export"): "analyst",
    ("GET", "/hub-link"): "admin",
    ("GET", "/hub-link/pseudonyms"): "admin",
    ("POST", "/hub-link/downloads"): "admin",
    ("GET", "/hub-link/downloads/{download_id}"): "admin",
    ("GET", "/hub-link/downloads/{download_id}/preview"): "admin",
}


def test_every_municipal_endpoint_per_role(linked: dict[str, Any]) -> None:
    app = linked["app"]
    routes = {
        (m.upper(), p)
        for p, ops in app.openapi()["paths"].items()
        if p.startswith(("/submissions", "/hub-link"))
        for m in ops
    }
    assert routes == set(MUNICIPAL_ENDPOINTS)
    roles = ("viewer", "analyst", "admin")
    zero = "00000000-0000-0000-0000-000000000000"
    for (method, path), lowest in MUNICIPAL_ENDPOINTS.items():
        url = path.replace("{submission_id}", zero).replace("{download_id}", zero)
        assert TestClient(app).request(method, url, json={}).status_code == 401
        for role in roles:
            code = _login(app, role).request(method, url, json={}).status_code
            if roles.index(role) < roles.index(lowest):
                assert code == 403, (role, method, path, code)
            else:
                assert code not in (401, 403), (role, method, path, code)
    # The hub has no such routes, and a municipal installation has no /hub routes.
    assert TestClient(linked["hub_app"]).get("/submissions").status_code == 404
    assert _login(app, "admin").get("/hub/installations").status_code == 404

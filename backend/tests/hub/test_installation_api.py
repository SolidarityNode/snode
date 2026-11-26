"""Hub side of municipal submissions: tokens, scope, idempotency, conflicts, offline files."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import uuid
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.hub.conftest import IMPORTS, hub_login, onboard
from tests.hub.test_publish import _area, _import_facilities, _publish


def _rows(file: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO((IMPORTS / file).read_text(encoding="utf-8")))
    return [{"row": n, "values": dict(r)} for n, r in enumerate(reader, start=2)]


def _payload(rows: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    body = {
        "id": str(uuid.uuid4()),
        "municipality_id": "M-A",
        "base_package_version": "1.0.0",
        "file_name": "change.csv",
        "comment": "from the municipality",
        "submitted_by": "u-0a1b2c3d",
        "submitter_role": "analyst",
        "rows": rows,
        "based_on": {},
    }
    body.update(extra)
    return body


@pytest.fixture
def hub_with_areas(
    hub_db: Session, hub_settings: Any, hub_worker: Any, demo_sources: None, hub_users: Any
) -> dict[str, Any]:
    """A and B onboarded with facilities, study areas a and b published, two installations."""
    from solidaritynode_backend.services.hub.installations import register_installation

    onboard(hub_db, hub_settings, hub_worker, "M-A")
    _import_facilities(hub_db, hub_settings, "M-A", "facilities-M-A.csv")
    _area(hub_db, hub_settings, "study-area-a", "M-A")
    _publish(hub_db, hub_settings, hub_worker, "study-area-a")
    onboard(hub_db, hub_settings, hub_worker, "M-B")
    _import_facilities(hub_db, hub_settings, "M-B", "facilities-M-B.csv")
    _area(hub_db, hub_settings, "study-area-b", "M-B")
    _publish(hub_db, hub_settings, hub_worker, "study-area-b")
    a, token_a = register_installation(hub_db, "Municipality A installation", "study-area-a", 1)
    b, token_b = register_installation(hub_db, "Municipality B installation", "study-area-b", 1)
    hub_db.commit()
    return {"a": a, "b": b, "token_a": token_a, "token_b": token_b}


def _client(app: Any, token: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_token_is_stored_hashed_and_shown_once(
    hub_with_areas: dict[str, Any], hub_db: Session, hub_app: Any
) -> None:
    token = hub_with_areas["token_a"]
    row = hub_db.execute(
        text(
            "SELECT token_hash, offline_key FROM hub_installations "
            "WHERE name LIKE 'Municipality A%'"
        )
    ).one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(dict(row._mapping))
    listed = hub_login(hub_app, "admin").get("/hub/installations").json()
    assert all("token" not in i for i in listed)
    assert token not in json.dumps(listed)


def test_token_scope(hub_with_areas: dict[str, Any], hub_app: Any) -> None:
    a = _client(hub_app, hub_with_areas["token_a"])
    b = _client(hub_app, hub_with_areas["token_b"])
    me = a.get("/hub/installation/me").json()
    assert me["study_area_id"] == "study-area-a"
    assert me["core_municipalities"] == ["M-A"]
    assert [p["version"] for p in me["packages"]] == ["1.0.0"]

    # Only core municipalities of its own study area (not its buffer M-B).
    refused = a.post(
        "/hub/installation/submissions",
        json=_payload(_rows("facilities-M-B.csv"), municipality_id="M-B"),
    )
    assert refused.status_code == 403
    assert "not a core municipality" in refused.json()["detail"]

    sent = a.post(
        "/hub/installation/submissions", json=_payload(_rows("facilities-M-A-update.csv"))
    )
    assert sent.status_code == 200, sent.text
    sid = sent.json()["id"]
    # B cannot read or withdraw A's submission, nor download A's packages.
    assert b.get("/hub/installation/submissions", params={"ids": [sid]}).json() == []
    assert b.post(f"/hub/installation/submissions/{sid}/withdraw").status_code == 404
    assert a.get("/hub/installation/packages/1.0.0/download").status_code == 200
    assert b.get("/hub/installation/packages/1.0.0/download").status_code == 200  # its own area
    own = b.get("/hub/installation/me").json()
    assert own["study_area_id"] == "study-area-b"
    # The download route serves only the token's own study area: A's archive differs from B's.
    a_zip = a.get("/hub/installation/packages/1.0.0/download").content
    b_zip = b.get("/hub/installation/packages/1.0.0/download").content
    assert a_zip != b_zip
    assert b"study-area-a" in zipfile.ZipFile(io.BytesIO(a_zip)).read("manifest.json")
    assert b"study-area-b" in zipfile.ZipFile(io.BytesIO(b_zip)).read("manifest.json")

    # No token, a wrong token, a session cookie: 401.
    assert TestClient(hub_app).get("/hub/installation/me").status_code == 401
    assert _client(hub_app, "sn_inst_wrong").get("/hub/installation/me").status_code == 401
    assert hub_login(hub_app, "admin").get("/hub/installation/me").status_code == 401


def test_revoked_and_rotated_tokens_fail(hub_with_areas: dict[str, Any], hub_app: Any) -> None:
    admin = hub_login(hub_app, "admin")
    inst_id = hub_with_areas["a"]["id"]
    old = hub_with_areas["token_a"]
    rotated = admin.post(f"/hub/installations/{inst_id}/token").json()["token"]
    assert _client(hub_app, old).get("/hub/installation/me").status_code == 401
    assert _client(hub_app, rotated).get("/hub/installation/me").status_code == 200
    assert admin.post(f"/hub/installations/{inst_id}/revoke").json()["active"] is False
    assert _client(hub_app, rotated).get("/hub/installation/me").status_code == 401


def test_resend_is_idempotent_and_withdraw_stops_at_review(
    hub_with_areas: dict[str, Any], hub_app: Any, hub_db: Session
) -> None:
    a = _client(hub_app, hub_with_areas["token_a"])
    payload = _payload(_rows("facilities-M-A-update.csv"))
    first = a.post("/hub/installation/submissions", json=payload).json()
    again = a.post("/hub/installation/submissions", json=payload).json()
    assert first["changeset_id"] == again["changeset_id"]
    assert first["state"] == "pending_review"
    count = hub_db.execute(
        text("SELECT count(*) FROM hub_changesets WHERE submission_uuid = :u"), {"u": payload["id"]}
    ).scalar_one()
    assert count == 1
    cs = hub_login(hub_app, "admin").get(f"/hub/changesets/{first['changeset_id']}").json()
    assert cs["kind"] == "submission"
    assert cs["source"] == (
        "submitted by municipality M-A (installation Municipality A installation, "
        "user u-0a1b2c3d, analyst)"
    )
    # Withdraw before review: allowed. After review starts: refused.
    other = _payload(_rows("facilities-M-A-update.csv"))
    second = a.post("/hub/installation/submissions", json=other).json()
    hub_login(hub_app, "admin").post(f"/hub/changesets/{second['changeset_id']}/review")
    refused = a.post(f"/hub/installation/submissions/{other['id']}/withdraw")
    assert refused.status_code == 409
    withdrawn = a.post(f"/hub/installation/submissions/{payload['id']}/withdraw").json()
    assert withdrawn["state"] == "withdrawn"


def test_validation_errors_reject_at_once(hub_with_areas: dict[str, Any], hub_app: Any) -> None:
    a = _client(hub_app, hub_with_areas["token_a"])
    result = a.post(
        "/hub/installation/submissions", json=_payload(_rows("facilities-M-A-errors.csv"))
    ).json()
    assert result["state"] == "rejected_by_validation"
    assert result["errors"] == 4


def test_conflicts_are_detected_resolved_per_item_and_visible_to_the_submitter(
    hub_with_areas: dict[str, Any], hub_app: Any, hub_db: Session, hub_settings: Any
) -> None:
    from solidaritynode_backend.services.hub.facilities import HubFeatureSource, manual_changeset

    based_on = {
        fid: {k: v for k, v in state.items() if k not in ("facility_id", "valid_to")}
        for fid, state in HubFeatureSource(hub_db, hub_settings).existing("M-A").items()
    }
    # The hub changes HF-000002 after the municipality's package 1.0.0.
    from solidaritynode_backend.services.hub.facilities import approve_changeset

    hub_edit = manual_changeset(
        hub_db,
        hub_settings,
        "M-A",
        "HF-000002",
        {"operating_hours": "Mon-Fri 09:00-13:00"},
        [],
        False,
        "hub correction",
        1,
    )
    approve_changeset(hub_db, hub_settings, hub_edit, 1)
    hub_db.commit()
    a = _client(hub_app, hub_with_areas["token_a"])
    sent = a.post(
        "/hub/installation/submissions",
        json=_payload(_rows("facilities-M-A-update.csv"), based_on=based_on),
    ).json()
    admin = hub_login(hub_app, "admin")
    cs = admin.get(f"/hub/changesets/{sent['changeset_id']}").json()
    conflicted = [i for i in cs["items"] if i["conflict"]]
    assert [i["facility_id"] for i in conflicted] == ["HF-000002"]
    conflict = conflicted[0]["conflict"]
    assert conflict["fields"] == ["operating_hours"]
    assert conflict["municipality"]["operating_hours"] == "Mon-Fri 08:00-16:00"
    assert conflict["hub"]["operating_hours"] == "Mon-Fri 09:00-13:00"
    refused = admin.post(f"/hub/changesets/{sent['changeset_id']}/approve", json={})
    assert refused.status_code == 409
    assert "has conflicts" in refused.json()["detail"]
    item_no = conflicted[0]["item_no"]
    approved = admin.post(
        f"/hub/changesets/{sent['changeset_id']}/approve",
        json={"comment": "kept our hours", "resolutions": {str(item_no): "hub"}},
    )
    assert approved.status_code == 200, approved.text
    hours = hub_db.execute(
        text(
            "SELECT properties->>'operating_hours' FROM hub_features WHERE feature_id = 'HF-000002'"
        )
    ).scalar_one()
    assert hours == "Mon-Fri 09:00-13:00"  # the hub's value was kept
    status = a.get("/hub/installation/submissions", params={"ids": [sent["id"]]}).json()[0]
    assert status["state"] == "approved"
    assert status["comment"] == "kept our hours"
    assert status["conflicts"] == [
        {"facility_id": "HF-000002", "fields": ["operating_hours"], "resolution": "hub"}
    ]


def _offline_file(token: str, installation_id: Any, payload: dict[str, Any]) -> bytes:
    from solidaritynode_backend.services.hub.installations import offline_key

    body = json.dumps(payload, sort_keys=True).encode()
    signature = hmac.new(bytes.fromhex(offline_key(token)), body, hashlib.sha256).hexdigest()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("submission.json", body)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "installation_id": str(installation_id),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            ),
        )
        archive.writestr("signature.txt", signature)
    return buffer.getvalue()


def test_offline_file_gives_the_same_changeset_as_online(
    hub_with_areas: dict[str, Any], hub_app: Any
) -> None:
    token = hub_with_areas["token_a"]
    inst_id = hub_with_areas["a"]["id"]
    admin = hub_login(hub_app, "admin")
    rows = _rows("facilities-M-A-update.csv")
    online = (
        _client(hub_app, token).post("/hub/installation/submissions", json=_payload(rows)).json()
    )
    offline_payload = _payload(rows)
    uploaded = admin.post(
        "/hub/submission-files",
        content=_offline_file(token, inst_id, offline_payload),
        headers={"Content-Type": "application/zip"},
    )
    assert uploaded.status_code == 201, uploaded.text
    on = admin.get(f"/hub/changesets/{online['changeset_id']}").json()
    off = uploaded.json()
    assert off["offline"] is True

    def strip(cs: dict[str, Any]) -> list[Any]:
        return [(i["action"], i["facility_id"], i["fields"], i["after"]) for i in cs["items"]]

    assert strip(on) == strip(off)
    assert on["report"]["summary"] == off["report"]["summary"]
    # Tampered content, or a signature made with another installation's key: refused.
    tampered = _offline_file(token, inst_id, _payload(rows))
    bad = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(tampered)) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            dst.writestr(
                name,
                data.replace(b"from the municipality", b"changed later")
                if name == "submission.json"
                else data,
            )
    assert admin.post("/hub/submission-files", content=bad.getvalue()).status_code == 422
    forged = _offline_file(hub_with_areas["token_b"], inst_id, _payload(rows))
    assert admin.post("/hub/submission-files", content=forged).status_code == 422

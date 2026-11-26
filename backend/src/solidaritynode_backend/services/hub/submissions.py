"""Facility submissions received from municipal installations (ADR 0014 Part A).

A submission arrives through the installation API (token, A2) or as an offline file (A3). The
hub:

1. checks the scope: a **core** municipality of the installation's study area;
2. is **idempotent** by the submission UUID chosen by the installation (a resend returns the
   existing changeset);
3. validates again with the same validator as file imports, on its curated features, drops
   anything that is not a template column, and stores a **pending changeset** (kind
   ``submission``) whose source names the municipality, installation, pseudonymous user and
   role; with validation errors it is rejected at once (``rejected_by_validation``);
4. marks **conflicts**: items whose facility changed in the hub since the package the
   municipality based them on; a hub administrator resolves each before approving.

The municipality can withdraw a submission until a hub administrator starts reviewing it.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import uuid
import zipfile
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.messages import msg
from solidaritynode_backend.services.hub.common import HubError, jsonb
from solidaritynode_backend.services.hub.facilities import (
    COLUMNS,
    ImportRequest,
    Parsed,
    changeset_detail,
    create_import,
    diff_fields,
)
from solidaritynode_backend.services.hub.publish import study_area_municipalities

__all__ = [
    "installation_packages",
    "receive",
    "start_review",
    "statuses",
    "value_of",
    "verify_offline_file",
    "withdraw",
]

MAX_ROWS_BYTES = 5 * 1024 * 1024


def value_of(state: Mapping[str, Any] | None, field: str) -> object:
    """Return a field of a facility state, ``services.<id>.<input>`` and ``location`` included."""
    if not state:
        return None
    if field == "location":
        return state.get("_xy")
    value: object = state
    for part in field.replace(" (added)", "").replace(" (removed)", "").split("."):
        value = value.get(part) if isinstance(value, Mapping) else None
    return value


def _study_area(db: Session, inst: Mapping[str, Any]) -> dict[str, Any]:
    row = (
        db.execute(
            text("SELECT * FROM hub_study_areas WHERE id = :s"), {"s": inst["study_area_id"]}
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("hub.submission.study_area_missing", status=409, id=inst["study_area_id"])
    return dict(row)


def _existing(db: Session, submission_id: uuid.UUID) -> RowMapping | None:
    return (
        db.execute(
            text("SELECT * FROM hub_changesets WHERE submission_uuid = :u"), {"u": submission_id}
        )
        .mappings()
        .one_or_none()
    )


def receive(
    db: Session,
    settings: Settings,
    inst: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    offline: bool = False,
) -> dict[str, Any]:
    """Store a submission as a pending changeset (or return the one already stored).

    Raises:
        HubError: Outside the installation's scope, a UUID used by another installation, or an
            unreadable payload.
    """
    submission_id = uuid.UUID(str(payload["id"]))
    found = _existing(db, submission_id)
    if found is not None:
        if found["installation_id"] != inst["id"]:
            raise HubError("hub.submission.other_installation", status=409, id=submission_id)
        return statuses(db, inst, [submission_id])[0]
    area = _study_area(db, inst)
    municipality = str(payload["municipality_id"])
    if municipality not in area["core_municipalities"]:
        raise HubError("hub.submission.not_core", status=403, municipality=municipality)
    rows = [
        (int(r["row"]), {k: str(v) for k, v in dict(r["values"]).items() if k in COLUMNS})
        for r in payload["rows"]
    ]
    data = json.dumps(payload["rows"], sort_keys=True).encode()
    if len(data) > MAX_ROWS_BYTES:
        raise HubError("hub.source.too_large", status=413, limit=MAX_ROWS_BYTES // 2**20)
    source = msg(
        "hub.submission.source",
        municipality=municipality,
        installation=inst["name"],
        user=payload["submitted_by"],
        role=payload["submitter_role"],
    )
    request = ImportRequest(
        municipality,
        source=source,
        comment=str(payload.get("comment") or ""),
        licence="CC-BY-4.0",
        attribution=msg("hub.submission.attribution", municipality=municipality),
        complete_list=bool(payload.get("complete_list")),
        is_correction=bool(payload.get("is_correction")),
    )
    changeset_id = create_import(
        db,
        settings,
        request,
        str(payload.get("file_name") or "submission"),
        data,
        None,
        kind="submission",
        parsed=Parsed(rows),
    )
    db.execute(
        text(
            "UPDATE hub_changesets SET installation_id = :i, submission_uuid = :u, "
            "submitted_by = :by, submitter_role = :role, base_package_version = :v, "
            "offline = :o WHERE id = :c"
        ),
        {
            "i": inst["id"],
            "u": submission_id,
            "by": payload["submitted_by"],
            "role": payload["submitter_role"],
            "v": payload.get("base_package_version"),
            "o": offline,
            "c": changeset_id,
        },
    )
    _mark_conflicts(db, changeset_id, payload.get("based_on") or {})
    detail = changeset_detail(db, changeset_id)
    if int(detail["report"].get("errors", 0)):
        db.execute(
            text(
                "UPDATE hub_changesets SET status = 'rejected', decided_at = now(), "
                "decision_comment = :c WHERE id = :id"
            ),
            {"c": msg("hub.submission.validation_failed"), "id": changeset_id},
        )
    return statuses(db, inst, [submission_id])[0]


def _mark_conflicts(
    db: Session, changeset_id: int, based_on: Mapping[str, Mapping[str, Any]]
) -> None:
    """Mark items whose facility changed in the hub since the municipality's package."""
    for item in changeset_detail(db, changeset_id)["items"]:
        fid = item["facility_id"]
        theirs = based_on.get(fid) if fid else None
        if item["action"] == "add" or theirs is None:
            continue
        ours = item["before"] or {}
        fields = diff_fields(theirs, ours)
        if not fields:
            continue
        conflict = {
            "fields": fields,
            "municipality": {f: value_of(theirs, f) for f in fields},
            "hub": {f: value_of(ours, f) for f in fields},
            "proposed": {f: value_of(item["after"], f) for f in fields},
        }
        db.execute(
            text(
                "UPDATE hub_changeset_items SET conflict = CAST(:c AS jsonb) "
                "WHERE changeset_id = :cs AND item_no = :n"
            ),
            {"c": jsonb(conflict), "cs": changeset_id, "n": item["item_no"]},
        )


def _state(row: Mapping[str, Any] | RowMapping) -> str:
    if row["status"] == "withdrawn":
        return "withdrawn"
    if row["status"] == "rejected":
        return "rejected" if row["decided_by"] is not None else "rejected_by_validation"
    if row["status"] == "approved":
        return "approved"
    return "pending_review"


def statuses(
    db: Session, inst: Mapping[str, Any], submission_ids: Iterable[uuid.UUID]
) -> list[dict[str, Any]]:
    """Return the hub's view of the installation's own submissions (others are not visible)."""
    ids = [uuid.UUID(str(i)) for i in submission_ids]
    out = []
    for row in db.execute(
        text(
            "SELECT c.*, d.username AS decided_by_name FROM hub_changesets c "
            "LEFT JOIN users d ON d.id = c.decided_by "
            "WHERE c.installation_id = :i AND c.submission_uuid = ANY(:ids)"
        ),
        {"i": inst["id"], "ids": ids},
    ).mappings():
        items = changeset_detail(db, int(row["id"]))["items"]
        out.append(
            {
                "id": str(row["submission_uuid"]),
                "changeset_id": int(row["id"]),
                "state": _state(row),
                "comment": row["decision_comment"] or "",
                "decided_at": row["decided_at"],
                "decided_by": row["decided_by_name"],
                "review_started": row["review_started_at"] is not None,
                "summary": row["report"].get("summary"),
                "errors": int(row["report"].get("errors", 0)),
                "entries": row["report"].get("entries", []),
                "conflicts": [
                    {
                        "facility_id": i["facility_id"],
                        "fields": (i["conflict"] or {}).get("fields", []),
                        "resolution": i["resolution"],
                    }
                    for i in items
                    if i.get("conflict")
                ],
            }
        )
    return out


def withdraw(db: Session, inst: Mapping[str, Any], submission_id: uuid.UUID) -> dict[str, Any]:
    """Withdraw a submission before the hub starts reviewing it.

    Raises:
        HubError: 404 if it is not this installation's; 409 once review started or decided.
    """
    row = (
        db.execute(
            text(
                "SELECT * FROM hub_changesets WHERE submission_uuid = :u AND installation_id = :i "
                "FOR UPDATE"
            ),
            {"u": submission_id, "i": inst["id"]},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("hub.submission.not_found", status=404, id=submission_id)
    if row["status"] != "withdrawn":
        if row["status"] != "pending" or row["review_started_at"] is not None:
            raise HubError("hub.submission.review_started", status=409, id=submission_id)
        db.execute(
            text(
                "UPDATE hub_changesets SET status = 'withdrawn', decided_at = now(), "
                "decision_comment = :c WHERE id = :id"
            ),
            {"c": msg("hub.submission.withdrawn_note"), "id": row["id"]},
        )
    return statuses(db, inst, [submission_id])[0]


def start_review(db: Session, changeset_id: int, user_id: int) -> None:
    """Record that a hub administrator started reviewing a submission (no withdrawal after)."""
    db.execute(
        text(
            "UPDATE hub_changesets SET review_started_at = now(), review_started_by = :u "
            "WHERE id = :id AND kind = 'submission' AND status = 'pending' "
            "AND review_started_at IS NULL"
        ),
        {"u": user_id, "id": changeset_id},
    )


def installation_packages(db: Session, inst: Mapping[str, Any]) -> dict[str, Any]:
    """Return the study area of an installation and its published package versions."""
    area = (
        db.execute(
            text("SELECT * FROM hub_study_areas WHERE id = :s"), {"s": inst["study_area_id"]}
        )
        .mappings()
        .one_or_none()
    )
    packages = []
    if area is not None:
        for row in db.execute(
            text(
                "SELECT version, created, published_at, archive_sha256, bytes, manifest "
                "FROM hub_packages WHERE study_area_id = :s AND status = 'published' "
                "ORDER BY published_at"
            ),
            {"s": inst["study_area_id"]},
        ).mappings():
            manifest = row["manifest"] or {}
            changesets = sorted(
                {
                    int(i["changeset_id"])
                    for p in manifest.get("provenance", [])
                    for i in p.get("inputs", [])
                    if i.get("changeset_id") is not None
                }
            )
            entry: dict[str, Any] = next(
                (c for c in manifest.get("changelog", []) if c.get("version") == row["version"]),
                {},
            )
            packages.append(
                {
                    "version": row["version"],
                    "created": row["created"],
                    "published_at": row["published_at"],
                    "archive_sha256": row["archive_sha256"],
                    "bytes": row["bytes"],
                    "changes": entry.get("changes", ""),
                    "changeset_ids": changesets,
                }
            )
    core = study_area_municipalities(db, dict(area))[0] if area is not None else []
    return {
        "installation_id": str(inst["id"]),
        "installation": inst["name"],
        "study_area_id": inst["study_area_id"],
        "study_area_registered": area is not None,
        "core_municipalities": core,
        "packages": packages,
    }


def verify_offline_file(db: Session, data: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Check an offline submission file; return its installation and the submission.

    Raises:
        HubError: If the archive, its checksum, its installation or its signature is wrong.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if names != {"submission.json", "manifest.json", "signature.txt"}:
                raise HubError("hub.submission.bad_file", detail="unexpected files")
            body = archive.read("submission.json")
            manifest = json.loads(archive.read("manifest.json"))
            signature = archive.read("signature.txt").decode().strip()
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError) as exc:
        raise HubError("hub.submission.bad_file", detail=type(exc).__name__) from None
    if hashlib.sha256(body).hexdigest() != manifest.get("sha256"):
        raise HubError("hub.submission.bad_file", detail="checksum mismatch")
    inst = (
        db.execute(
            text(
                "SELECT * FROM hub_installations WHERE id = CAST(:i AS uuid) AND revoked_at IS NULL"
            ),
            {"i": str(manifest.get("installation_id"))},
        )
        .mappings()
        .one_or_none()
    )
    if inst is None or not inst["offline_key"]:
        raise HubError("hub.submission.bad_signature")
    expected = hmac.new(bytes.fromhex(inst["offline_key"]), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HubError("hub.submission.bad_signature")
    return dict(inst), json.loads(body)

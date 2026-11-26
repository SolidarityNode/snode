"""Facility submissions from a municipal installation to the hub (ADR 0014 Part A).

An analyst or administrator proposes facility changes to the hub. A submission never changes
the installation's active data: the hub validates it, a hub administrator approves or rejects
it and publishes a new package version, and an administrator here imports that version with
the usual preview and confirm.

* **Local validation first**, with the hub's own validator
  (:mod:`solidaritynode_backend.services.hub.facilities`) on the facilities of the active data
  version (:class:`~solidaritynode_backend.services.hub.facilities.DataVersionFeatureSource`):
  personal-data columns and values are dropped here. Only the sanitised template rows, the
  changeset and the comment leave the installation; never the original file.
* **Who submitted** travels as a stable pseudonymous id per user (``u-…``) and the role; only
  this installation can resolve it (:func:`pseudonyms`, administrators only).
* **Lifecycle** (``submissions.status``): ``draft → sent → received → rejected_by_validation |
  pending_review → approved | rejected → published → imported``, and ``withdrawn``; every
  transition is stored in ``submission_events``.
* **Every network call runs in the worker** (``hub_sync`` and ``hub_download``, ADR 0006), never
  in a request handler; the screens read the stored status. The installation opens every
  connection (ADR 0012).
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, RowMapping, select, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.jobs import JobContext, PostgresJobRunner
from solidaritynode_backend.messages import msg
from solidaritynode_backend.orm import DataVersion
from solidaritynode_backend.services.hub.common import HubError, check, jsonb
from solidaritynode_backend.services.hub.facilities import (
    DataVersionFeatureSource,
    ImportRequest,
    Parsed,
    build_changeset,
    manual_rows,
    parse_file,
)
from solidaritynode_backend.services.hub.installations import offline_key
from solidaritynode_backend.services.packages import stage_upload

__all__ = [
    "DOWNLOAD_JOB_KIND",
    "SYNC_JOB_KIND",
    "HubUnreachableError",
    "create_draft",
    "export_offline",
    "hub_link",
    "manual_draft",
    "mark_imported",
    "payload",
    "pseudonyms",
    "queue_sync",
    "request_download",
    "run_download",
    "run_sync",
    "send",
    "withdraw",
]

log = logging.getLogger("solidaritynode.submissions")

SYNC_JOB_KIND = "hub_sync"
DOWNLOAD_JOB_KIND = "hub_download"
SYNC_LOCK = 772_014  # advisory lock: at most one sync at a time (ADR 0014 A5)
BACKOFF_FIRST_S = 60
BACKOFF_MAX_S = 3600
TIMEOUT_S = 30
STATUSES = (
    "draft",
    "sent",
    "received",
    "rejected_by_validation",
    "pending_review",
    "approved",
    "rejected",
    "published",
    "imported",
    "withdrawn",
)
POLLED = ("sent", "received", "pending_review", "approved")


type Row = Mapping[str, Any] | RowMapping


class HubUnreachableError(RuntimeError):
    """The hub did not answer (network, DNS, timeout, TLS)."""


# --- Talking to the hub (worker only) ---------------------------------------------------------

type Transport = Callable[[str, str, Mapping[str, str], bytes | None], tuple[int, bytes]]


def urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> tuple[int, bytes]:
    """Send one HTTP request with the standard library (TLS certificates verified)."""
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise HubUnreachableError(str(getattr(exc, "reason", exc))) from None


TRANSPORT: Transport = urllib_transport
"""The transport used by the worker; tests replace it with one that calls a hub app."""


class HubClient:
    """The hub's installation API, authenticated by the installation token."""

    def __init__(self, settings: Settings, transport: Transport | None = None) -> None:
        """Use the configured hub address and token."""
        self.base = settings.hub_url.rstrip("/")
        self.token = settings.hub_token.get_secret_value()
        self.transport = transport or TRANSPORT

    def call(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[int, Any]:
        """Return ``(status, JSON or bytes)``; raise :class:`HubUnreachableError`."""
        query = "?" + urllib.parse.urlencode(params, doseq=True) if params else ""
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, default=str).encode()
            headers["Content-Type"] = "application/json"
        status, content = self.transport(method, f"{self.base}{path}{query}", headers, data)
        try:
            return status, json.loads(content) if content[:1] in (b"{", b"[") else content
        except ValueError:
            return status, content


# --- Pseudonyms ---------------------------------------------------------------------------------


def pseudonym(db: Session, user_id: int) -> str:
    """Return the stable pseudonymous id of a user (created on first use)."""
    found = db.execute(
        text("SELECT pseudonym FROM user_pseudonyms WHERE user_id = :u"), {"u": user_id}
    ).scalar_one_or_none()
    if found is not None:
        return str(found)
    value = "u-" + secrets.token_hex(4)
    db.execute(
        text("INSERT INTO user_pseudonyms (user_id, pseudonym) VALUES (:u, :p)"),
        {"u": user_id, "p": value},
    )
    return value


def pseudonyms(db: Session) -> list[dict[str, Any]]:
    """Return the mapping pseudonym → username (administrators of this installation only)."""
    return [
        dict(r)
        for r in db.execute(
            text(
                "SELECT p.pseudonym, u.username, u.role FROM user_pseudonyms p "
                "JOIN users u ON u.id = p.user_id ORDER BY u.username"
            )
        ).mappings()
    ]


# --- Drafts -------------------------------------------------------------------------------------


def _active(db: Session) -> DataVersion:
    dv = db.scalar(select(DataVersion).where(DataVersion.active))
    if dv is None:
        raise HubError("error.no_data", status=409)
    return dv


def _event(
    db: Session,
    submission_id: uuid.UUID,
    old: str | None,
    new: str,
    *,
    user_id: int | None = None,
    hub: str | None = None,
    note: str = "",
) -> None:
    db.execute(
        text(
            "INSERT INTO submission_events (submission_id, from_status, to_status, by_user, "
            "by_hub, note) VALUES (:s, :f, :t, :u, :h, :n)"
        ),
        {"s": submission_id, "f": old, "t": new, "u": user_id, "h": hub, "n": note},
    )


def _store_draft(
    db: Session,
    settings: Settings,
    user_id: int,
    municipality: str,
    kind: str,
    file_name: str,
    parsed: Parsed,
    comment: str,
    complete_list: bool,
    is_correction: bool,
) -> uuid.UUID:
    dv = _active(db)
    source = DataVersionFeatureSource(db, dv.id)
    request = ImportRequest(
        municipality,
        source="municipal submission",
        complete_list=complete_list,
        is_correction=is_correction,
    )
    items, report = build_changeset(db, settings, request, parsed, source)
    summary = {a: sum(1 for i in items if i["action"] == a) for a in ("add", "update", "close")}
    if complete_list:
        report.append(
            check(
                "hub.import.complete_list",
                "warning",
                count=summary["close"],
                municipality=municipality,
            )
        )
    stored_report = {
        "file": file_name,
        "rows": len(parsed.rows),
        "entries": report,
        "errors": sum(1 for c in report if c["severity"] == "error"),
        "warnings": sum(1 for c in report if c["severity"] == "warning"),
        "summary": summary,
    }
    # The rows as validated: template columns only, personal values already cleared.
    rows = [{"row": n, "values": values} for n, values in parsed.rows]
    submission_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO submissions (id, municipality_id, kind, data_version_id, package_id, "
            "base_package_version, file_name, comment, complete_list, is_correction, rows, "
            "report, items, created_by) VALUES (:id, :m, :k, :dv, :pkg, :v, :f, :c, :cl, :corr, "
            "CAST(:rows AS jsonb), CAST(:r AS jsonb), CAST(:i AS jsonb), :u)"
        ),
        {
            "id": submission_id,
            "m": municipality,
            "k": kind,
            "dv": dv.id,
            "pkg": dv.package_id,
            "v": dv.version,
            "f": file_name,
            "c": comment,
            "cl": complete_list,
            "corr": is_correction,
            "rows": jsonb(rows),
            "r": jsonb(stored_report),
            "i": jsonb(items),
            "u": user_id,
        },
    )
    pseudonym(db, user_id)
    _event(db, submission_id, None, "draft", user_id=user_id)
    return submission_id


def create_draft(
    db: Session,
    settings: Settings,
    user_id: int,
    municipality: str,
    file_name: str,
    data: bytes,
    comment: str = "",
    complete_list: bool = False,
    is_correction: bool = False,
) -> uuid.UUID:
    """Validate an uploaded template file locally and store it as a draft.

    Raises:
        HubError: On a file that cannot be read, a municipality that is not core, no data.
    """
    if len(data) > settings.hub_max_facility_file_mb * 1024 * 1024:
        raise HubError("hub.source.too_large", status=413, limit=settings.hub_max_facility_file_mb)
    parsed = parse_file(settings, file_name, data)
    return _store_draft(
        db,
        settings,
        user_id,
        municipality,
        "import",
        file_name,
        parsed,
        comment,
        complete_list,
        is_correction,
    )


def manual_draft(
    db: Session,
    settings: Settings,
    user_id: int,
    municipality: str,
    facility_id: str | None,
    values: Mapping[str, Any],
    services: list[Mapping[str, Any]],
    close: bool,
    comment: str,
) -> uuid.UUID:
    """Turn the edit form into template rows and store a validated draft.

    Raises:
        HubError: If the facility is not in the active data version.
    """
    dv = _active(db)
    current = None
    if facility_id:
        current = DataVersionFeatureSource(db, dv.id).existing(municipality).get(facility_id)
        if current is None:
            raise HubError("hub.error.facility_not_found", status=404, id=facility_id)
    rows = manual_rows(current, municipality, facility_id, values, services, close)
    return _store_draft(
        db,
        settings,
        user_id,
        municipality,
        "manual",
        "edit form",
        Parsed(rows),
        comment,
        False,
        False,
    )


# --- Reading ------------------------------------------------------------------------------------

_COLUMNS = "s.*, u.username AS created_by_name, p.pseudonym AS submitted_by"


def get(db: Session, submission_id: uuid.UUID, *, lock: bool = False) -> dict[str, Any]:
    """Return one submission with its history.

    Raises:
        HubError: If it does not exist.
    """
    row = (
        db.execute(
            text(
                f"SELECT {_COLUMNS} FROM submissions s LEFT JOIN users u ON u.id = s.created_by "
                "LEFT JOIN user_pseudonyms p ON p.user_id = s.created_by WHERE s.id = :i"
                + (" FOR UPDATE OF s" if lock else "")
            ),
            {"i": submission_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("submission.not_found", status=404, id=submission_id)
    out = dict(row)
    out["summary"] = out["report"].get("summary")
    out["errors"] = out["report"].get("errors")
    out["events"] = [
        dict(e)
        for e in db.execute(
            text(
                "SELECT e.from_status, e.to_status, u.username AS by_user, e.by_hub, e.at, e.note "
                "FROM submission_events e LEFT JOIN users u ON u.id = e.by_user "
                "WHERE e.submission_id = :i ORDER BY e.id"
            ),
            {"i": submission_id},
        ).mappings()
    ]
    return out


def list_submissions(db: Session) -> list[dict[str, Any]]:
    """Return every submission, newest first (without rows and items)."""
    return [
        dict(r)
        for r in db.execute(
            text(
                "SELECT s.id, s.municipality_id, s.kind, s.status, s.file_name, s.comment, "
                "s.complete_list, s.created_at, s.sent_at, s.offline, s.last_error, "
                "s.next_attempt_at, s.hub_comment, s.published_in, s.imported_in, "
                "s.withdraw_requested, s.report->'summary' AS summary, "
                "(s.report->>'errors')::int AS errors, u.username AS created_by_name "
                "FROM submissions s LEFT JOIN users u ON u.id = s.created_by "
                "ORDER BY s.created_at DESC"
            )
        ).mappings()
    ]


# --- Sending, withdrawing, offline files --------------------------------------------------------


def queue_sync(db: Session) -> bool:
    """Queue one ``hub_sync`` job unless one is queued or running; return whether queued."""
    busy = db.execute(
        text("SELECT 1 FROM jobs WHERE kind = :k AND status IN ('queued', 'running') LIMIT 1"),
        {"k": SYNC_JOB_KIND},
    ).first()
    if busy:
        return False
    PostgresJobRunner(db).submit(SYNC_JOB_KIND, {})
    return True


def _set_status(
    db: Session,
    sub: Row,
    new: str,
    *,
    user_id: int | None = None,
    hub: str | None = None,
    note: str = "",
    **fields: object,
) -> None:
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(
        text(
            f"UPDATE submissions SET status = :st, updated_at = now()"
            f"{', ' + assignments if assignments else ''} WHERE id = :id"
        ),
        {"st": new, "id": sub["id"], **fields},
    )
    if new != sub["status"]:
        _event(db, sub["id"], sub["status"], new, user_id=user_id, hub=hub, note=note)


def send(
    db: Session,
    settings: Settings,
    user_id: int,
    submission_id: uuid.UUID,
    confirm_close: int | None,
) -> dict[str, Any]:
    """Queue a draft for the hub (the worker sends it).

    Raises:
        HubError: If it is not a draft, has errors, a complete list is not confirmed with the
            number of closures, or no hub is configured.
    """
    sub = get(db, submission_id, lock=True)
    if sub["status"] != "draft":
        raise HubError("submission.not_draft", status=409, id=submission_id)
    if int(sub["report"].get("errors", 0)):
        raise HubError("submission.has_errors", status=409, id=submission_id)
    closing = sum(1 for i in sub["items"] if i["action"] == "close")
    if sub["complete_list"] and confirm_close != closing:
        raise HubError(
            "hub.import.confirm_close",
            status=409,
            count=closing,
            municipality=sub["municipality_id"],
        )
    if not (settings.hub_url and settings.hub_token.get_secret_value()):
        raise HubError("submission.no_hub", status=409)
    now = datetime.now(UTC)
    _set_status(db, sub, "sent", user_id=user_id, sent_at=now, next_attempt_at=now, attempts=0)
    if settings.hub_link_enabled:
        queue_sync(db)
    return get(db, submission_id)


def withdraw(
    db: Session, settings: Settings, user_id: int, is_admin: bool, submission_id: uuid.UUID
) -> dict[str, Any]:
    """Withdraw a submission (its submitter or an administrator).

    A draft, or a submission the hub has not received yet, is withdrawn at once; one the hub
    received is withdrawn by the next sync, unless the hub has started reviewing it.

    Raises:
        HubError: If the user may not withdraw it, or it is past review.
    """
    sub = get(db, submission_id, lock=True)
    if not is_admin and sub["created_by"] != user_id:
        raise HubError("submission.only_submitter", status=403)
    if sub["status"] == "draft" or (
        sub["status"] == "sent" and sub["hub_changeset_id"] is None and not sub["offline"]
    ):
        _set_status(db, sub, "withdrawn", user_id=user_id)
    elif sub["status"] in ("received", "pending_review") or (
        sub["status"] == "sent" and sub["offline"]
    ):
        db.execute(
            text("UPDATE submissions SET withdraw_requested = true WHERE id = :i"),
            {"i": submission_id},
        )
        _event(
            db,
            submission_id,
            sub["status"],
            sub["status"],
            user_id=user_id,
            note=msg("submission.withdraw_requested"),
        )
        if settings.hub_link_enabled:
            queue_sync(db)
    else:
        raise HubError("submission.not_withdrawable", status=409, id=submission_id)
    return get(db, submission_id)


def payload(db: Session, sub: Row) -> dict[str, Any]:
    """Return exactly what is sent to the hub: sanitised rows, changeset basis, pseudonym."""
    role = db.execute(
        text("SELECT role FROM users WHERE id = :u"), {"u": sub["created_by"]}
    ).scalar_one_or_none()
    based_on = {
        str(i["facility_id"]): {
            k: v for k, v in (i["before"] or {}).items() if k not in ("facility_id", "valid_to")
        }
        for i in sub["items"]
        if i["action"] in ("update", "close") and i.get("facility_id") and i.get("before")
    }
    return {
        "id": str(sub["id"]),
        "municipality_id": sub["municipality_id"],
        "base_package_version": sub["base_package_version"],
        "file_name": sub["file_name"] or "",
        "comment": sub["comment"],
        "complete_list": bool(sub["complete_list"]),
        "is_correction": bool(sub["is_correction"]),
        "submitted_by": pseudonym(db, int(sub["created_by"])),
        "submitter_role": "admin" if role == "admin" else "analyst",
        "rows": sub["rows"],
        "based_on": based_on,
    }


def export_offline(
    db: Session, settings: Settings, user_id: int, submission_id: uuid.UUID
) -> tuple[bytes, str]:
    """Return the offline submission file of a draft (or of one already exported).

    The archive holds ``submission.json`` (the same content as an online submission),
    ``manifest.json`` (installation id, SHA-256) and ``signature.txt`` (HMAC-SHA256 with the
    key derived from the installation token, ADR 0014 A2–A3).

    Raises:
        HubError: Without a token or installation id, or for a submission past ``sent``.
    """
    sub = get(db, submission_id, lock=True)
    if sub["status"] not in ("draft", "sent") or (sub["status"] == "sent" and not sub["offline"]):
        raise HubError("submission.not_draft", status=409, id=submission_id)
    if int(sub["report"].get("errors", 0)):
        raise HubError("submission.has_errors", status=409, id=submission_id)
    token = settings.hub_token.get_secret_value()
    installation = hub_link(db, settings)["installation_id"]
    if not token or not installation:
        raise HubError("submission.no_token", status=409)
    body = json.dumps(payload(db, sub), sort_keys=True).encode()
    signature = hmac.new(bytes.fromhex(offline_key(token)), body, hashlib.sha256).hexdigest()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("submission.json", body)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "installation_id": installation,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "format": "solidaritynode-submission",
                    "version": 1,
                },
                sort_keys=True,
            ),
        )
        archive.writestr("signature.txt", signature)
    if sub["status"] == "draft":
        _set_status(db, sub, "sent", user_id=user_id, sent_at=datetime.now(UTC), offline=True)
    return buffer.getvalue(), f"submission-{submission_id}.zip"


# --- Connection state and downloads -------------------------------------------------------------


def hub_link(db: Session, settings: Settings) -> dict[str, Any]:
    """Return the hub connection as stored by the last sync (never the token)."""
    row = dict(db.execute(text("SELECT * FROM hub_link WHERE id = 1")).mappings().one())
    active = db.scalar(select(DataVersion).where(DataVersion.active))
    imported = {
        str(v)
        for (v,) in db.execute(
            text("SELECT version FROM data_versions WHERE package_id = :p"),
            {"p": row["study_area_id"] or ""},
        )
    }
    newer = [
        p
        for p in row["packages"]
        if p["version"] not in imported
        and (
            active is None
            or active.package_id != row["study_area_id"]
            or _semver(p["version"]) > _semver(active.version)
        )
    ]
    downloads = [
        dict(d)
        for d in db.execute(
            text(
                "SELECT d.id, d.version, d.status, d.staging_id, d.error, d.requested_at, "
                "u.username AS requested_by FROM hub_downloads d "
                "LEFT JOIN users u ON u.id = d.requested_by ORDER BY d.requested_at DESC LIMIT 20"
            )
        ).mappings()
    ]
    return {
        "configured": bool(settings.hub_url),
        "hub_url": settings.hub_url,
        "token_present": bool(settings.hub_token.get_secret_value()),
        "sync_enabled": settings.hub_link_enabled,
        "sync_seconds": settings.hub_sync_seconds,
        "installation_id": row.get("installation_id"),
        "installation_name": row["installation_name"],
        "study_area_id": row["study_area_id"],
        "last_sync_at": row["last_sync_at"],
        "last_contact_at": row["last_contact_at"],
        "last_error": row["last_error"],
        "packages": row["packages"],
        "active_version": active.version if active else None,
        "new_versions": newer,
        "downloads": downloads,
    }


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def request_download(db: Session, user_id: int, version: str) -> uuid.UUID:
    """Queue the download of a package version listed by the hub (administrators).

    Raises:
        HubError: If the hub has not listed that version.
    """
    packages = db.execute(text("SELECT packages FROM hub_link WHERE id = 1")).scalar_one()
    if not any(p["version"] == version for p in packages):
        raise HubError("submission.no_such_version", status=404, version=version)
    download_id = uuid.uuid4()
    job_id = PostgresJobRunner(db).submit(DOWNLOAD_JOB_KIND, {"download_id": str(download_id)})
    db.execute(
        text(
            "INSERT INTO hub_downloads (id, version, status, job_id, requested_by) "
            "VALUES (:i, :v, 'queued', CAST(:j AS uuid), :u)"
        ),
        {"i": download_id, "v": version, "j": job_id, "u": user_id},
    )
    return download_id


def mark_imported(db: Session) -> int:
    """Mark published submissions as imported once their version (or a later one) is here."""
    study_area = db.execute(text("SELECT study_area_id FROM hub_link WHERE id = 1")).scalar_one()
    versions = sorted(
        (
            str(v)
            for (v,) in db.execute(
                text("SELECT version FROM data_versions WHERE package_id = :p"),
                {"p": study_area or ""},
            )
        ),
        key=_semver,
    )
    count = 0
    for sub in db.execute(
        text("SELECT * FROM submissions WHERE status = 'published' AND published_in IS NOT NULL")
    ).mappings():
        later = [v for v in versions if _semver(v) >= _semver(sub["published_in"])]
        if later:
            _set_status(db, sub, "imported", imported_in=later[0])
            count += 1
    return count


# --- The worker jobs ----------------------------------------------------------------------------


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(BACKOFF_FIRST_S * 2 ** max(attempts - 1, 0), BACKOFF_MAX_S))


def _apply(db: Session, sub: Row, remote: Mapping[str, Any]) -> None:
    """Store the hub's view of a submission and the transitions it implies."""
    state = str(remote["state"])
    db.execute(
        text(
            "UPDATE submissions SET hub_changeset_id = :c, hub_comment = :m, "
            "hub_decided_at = :d, hub_conflicts = CAST(:x AS jsonb), last_error = NULL, "
            "withdraw_requested = CASE WHEN :st = 'withdrawn' THEN false "
            "ELSE withdraw_requested END, updated_at = now() WHERE id = :i"
        ),
        {
            "c": remote["changeset_id"],
            "m": remote.get("comment") or None,
            "d": remote.get("decided_at"),
            "x": jsonb(remote.get("conflicts") or []),
            "st": state,
            "i": sub["id"],
        },
    )
    status = str(sub["status"])
    if status == "sent":
        _set_status(db, {"id": sub["id"], "status": status}, "received", hub="hub")
        status = "received"
    if status in ("published", "imported") or state == status:
        return
    _set_status(
        db,
        {"id": sub["id"], "status": status},
        state,
        hub=str(remote.get("decided_by") or "hub"),
        note=str(remote.get("comment") or ""),
    )


def _record_link(db: Session, **fields: object) -> None:
    assignments = ", ".join(
        f"{k} = CAST(:{k} AS jsonb)" if k == "packages" else f"{k} = :{k}" for k in fields
    )
    db.execute(text(f"UPDATE hub_link SET {assignments}, updated_at = now() WHERE id = 1"), fields)


def _due(db: Session) -> list[RowMapping]:
    return list(
        db.execute(
            text(
                "SELECT * FROM submissions WHERE status = 'sent' AND NOT offline "
                "AND hub_changeset_id IS NULL AND (next_attempt_at IS NULL "
                "OR next_attempt_at <= now()) ORDER BY sent_at FOR UPDATE SKIP LOCKED"
            )
        ).mappings()
    )


def _unreachable(db: Session, error: str) -> None:
    now = datetime.now(UTC)
    for sub in _due(db):
        attempts = int(sub["attempts"]) + 1
        db.execute(
            text(
                "UPDATE submissions SET attempts = :a, next_attempt_at = :n, last_error = :e "
                "WHERE id = :i"
            ),
            {"a": attempts, "n": now + _backoff(attempts), "e": error, "i": sub["id"]},
        )
    _record_link(db, last_sync_at=now, last_error=error)


def sync(db: Session, settings: Settings, client: HubClient, ctx: JobContext | None = None) -> None:
    """One synchronisation with the hub: sends, withdrawals, statuses, packages, imports.

    If the hub cannot be reached at any point, the submissions still due get their next try
    (exponential backoff) and the error is recorded; nothing is lost and nothing is sent twice
    (the hub is idempotent by submission id).
    """
    try:
        _sync(db, client, ctx)
    except HubUnreachableError as exc:
        _unreachable(db, msg("submission.hub_unreachable", detail=str(exc)))


def _sync(db: Session, client: HubClient, ctx: JobContext | None) -> None:
    def step(fraction: float) -> None:
        if ctx is not None:
            ctx.progress(fraction)

    now = datetime.now(UTC)
    status, me = client.call("GET", "/hub/installation/me")
    if status != 200:
        _unreachable(db, msg("submission.hub_refused", status=status))
        return
    _record_link(
        db,
        last_sync_at=now,
        last_contact_at=now,
        last_error=None,
        installation_id=me["installation_id"],
        installation_name=me["installation"],
        study_area_id=me["study_area_id"],
        packages=jsonb(me["packages"]),
    )
    step(0.2)
    for sub in _due(db):
        code, body = client.call("POST", "/hub/installation/submissions", payload(db, sub))
        if code == 200:
            _apply(db, sub, body)
        elif code in (400, 403, 404, 409, 413, 422):
            detail = body.get("detail") if isinstance(body, dict) else str(body)
            _set_status(
                db,
                sub,
                "rejected_by_validation",
                hub="hub",
                note=str(detail),
                hub_comment=str(detail),
            )
        else:
            attempts = int(sub["attempts"]) + 1
            db.execute(
                text(
                    "UPDATE submissions SET attempts = :a, next_attempt_at = :n, "
                    "last_error = :e WHERE id = :i"
                ),
                {
                    "a": attempts,
                    "n": now + _backoff(attempts),
                    "e": msg("submission.hub_refused", status=code),
                    "i": sub["id"],
                },
            )
    step(0.5)
    for sub in db.execute(
        text("SELECT * FROM submissions WHERE withdraw_requested AND hub_changeset_id IS NOT NULL")
    ).mappings():
        code, body = client.call("POST", f"/hub/installation/submissions/{sub['id']}/withdraw")
        if code == 200:
            _apply(db, sub, body)
        elif code == 409:
            db.execute(
                text("UPDATE submissions SET withdraw_requested = false WHERE id = :i"),
                {"i": sub["id"]},
            )
            _event(
                db,
                sub["id"],
                sub["status"],
                sub["status"],
                hub="hub",
                note=msg("submission.withdraw_refused"),
            )
    step(0.7)
    polled = list(
        db.execute(
            text(
                "SELECT * FROM submissions WHERE status = ANY(:s) "
                "AND (hub_changeset_id IS NOT NULL OR offline)"
            ),
            {"s": list(POLLED)},
        ).mappings()
    )
    if polled:
        code, remote = client.call(
            "GET", "/hub/installation/submissions", params={"ids": [str(s["id"]) for s in polled]}
        )
        if code == 200:
            by_id = {r["id"]: r for r in remote}
            for sub in polled:
                if str(sub["id"]) in by_id:
                    _apply(db, sub, by_id[str(sub["id"])])
    step(0.85)
    for sub in db.execute(text("SELECT * FROM submissions WHERE status = 'approved'")).mappings():
        version = next(
            (p["version"] for p in me["packages"] if sub["hub_changeset_id"] in p["changeset_ids"]),
            None,
        )
        if version:
            _set_status(db, sub, "published", hub="hub", published_in=version)
    mark_imported(db)
    step(0.95)


def run_sync(
    engine: Engine, settings: Settings, ctx: JobContext, payload_: Mapping[str, Any]
) -> None:
    """Worker handler of ``hub_sync``: at most one runs at a time (advisory lock)."""
    if not settings.hub_link_enabled:
        return
    with engine.connect() as lock:
        if not lock.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SYNC_LOCK}).scalar():
            return
        try:
            with Session(engine) as db:
                sync(db, settings, HubClient(settings), ctx)
                db.commit()
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SYNC_LOCK})
            lock.commit()


def queue_sync_periodic(engine: Engine) -> None:
    """The worker's periodic tick (ADR 0006, 0014 A5): queue a sync unless one is pending."""
    with Session(engine) as db:
        if queue_sync(db):
            db.commit()


def run_download(
    engine: Engine, settings: Settings, ctx: JobContext, payload_: Mapping[str, Any]
) -> None:
    """Worker handler of ``hub_download``: fetch a package and check its SHA-256."""
    download_id = uuid.UUID(str(payload_["download_id"]))
    with Session(engine) as db:
        row = (
            db.execute(text("SELECT * FROM hub_downloads WHERE id = :i"), {"i": download_id})
            .mappings()
            .one()
        )
        packages = db.execute(text("SELECT packages FROM hub_link WHERE id = 1")).scalar_one()
        expected = next((p for p in packages if p["version"] == row["version"]), None)
        error: str | None = None
        staging_id: str | None = None
        digest: str | None = None
        try:
            if expected is None:
                raise HubError("submission.no_such_version", version=row["version"])
            ctx.progress(0.1)
            code, body = HubClient(settings).call(
                "GET", f"/hub/installation/packages/{row['version']}/download"
            )
            if code != 200 or not isinstance(body, bytes):
                raise HubError("submission.hub_refused", status=code)
            digest = hashlib.sha256(body).hexdigest()
            if digest != expected["archive_sha256"]:
                raise HubError("submission.checksum_mismatch", version=row["version"])
            staging_id = stage_upload(settings, body)
        except (HubError, HubUnreachableError) as exc:
            error = (
                str(exc)
                if isinstance(exc, HubError)
                else msg("submission.hub_unreachable", detail=str(exc))
            )
        db.execute(
            text(
                "UPDATE hub_downloads SET status = :s, staging_id = :st, sha256 = :d, error = :e "
                "WHERE id = :i"
            ),
            {
                "s": "failed" if error else "done",
                "st": staging_id,
                "d": digest,
                "e": error,
                "i": download_id,
            },
        )
        db.commit()

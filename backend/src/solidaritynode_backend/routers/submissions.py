"""Submissions to the hub and the hub connection (ADR 0014 Part A): municipal installations.

Mounted only when ``DEPLOYMENT_MODE=municipality``. **Analysts and administrators** submit;
viewers see nothing. Only **administrators** see the hub connection, the pseudonym mapping and
download new package versions (import stays the existing preview and confirm). No handler calls
the hub: sending, polling and downloading run in the worker; "check now" only queues a sync.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import Principal, require_role
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.messages import msg
from solidaritynode_backend.schemas.api import PreviewOut
from solidaritynode_backend.schemas.submissions import (
    DownloadIn,
    DownloadOut,
    HubLinkOut,
    PseudonymOut,
    SendIn,
    SubmissionEditIn,
    SubmissionOut,
    SubmissionSummaryOut,
)
from solidaritynode_backend.services import submissions as subs
from solidaritynode_backend.services.hub.common import HubError
from solidaritynode_backend.services.hub.facilities import EXTENSIONS

router = APIRouter(tags=["submissions"])

Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]
Editor = Annotated[Principal, Depends(require_role("admin", "analyst"))]
Admin = Annotated[Principal, Depends(require_role("admin"))]


def _fail(exc: HubError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def _one(db: Session, submission_id: uuid.UUID) -> SubmissionOut:
    try:
        return SubmissionOut(**subs.get(db, submission_id))
    except HubError as exc:
        raise _fail(exc) from None


@router.get("/submissions", response_model=list[SubmissionSummaryOut])
def list_submissions(_: Editor, db: Db) -> list[dict[str, Any]]:
    """Every submission of this installation, newest first."""
    return subs.list_submissions(db)


@router.post(
    "/submissions/upload",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
            "required": True,
        }
    },
)
async def upload(
    request: Request,
    user: Editor,
    db: Db,
    settings: Config,
    municipality: Annotated[str, Query(min_length=1)],
    file_name: Annotated[str, Query(min_length=1)],
    comment: str = "",
    complete_list: bool = False,
    is_correction: bool = False,
) -> SubmissionOut:
    """Check a template file **locally** and keep it as a draft (nothing is sent yet)."""
    if Path(file_name).suffix.lower() not in EXTENSIONS:
        raise _fail(HubError("hub.import.unsupported_type", file=file_name))
    limit = int(settings.hub_max_facility_file_mb * 1024 * 1024)
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise _fail(
                HubError(
                    "hub.source.too_large", status=413, limit=settings.hub_max_facility_file_mb
                )
            )

    def work() -> uuid.UUID:
        return subs.create_draft(
            db,
            settings,
            user.id,
            municipality,
            file_name,
            bytes(data),
            comment,
            complete_list,
            is_correction,
        )

    try:
        submission_id = await run_in_threadpool(work)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _one(db, submission_id)


@router.post(
    "/submissions/edits", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED
)
def edit(body: SubmissionEditIn, user: Editor, db: Db, settings: Config) -> SubmissionOut:
    """Propose a change to one facility of the active data with the form (a draft)."""
    try:
        submission_id = subs.manual_draft(
            db,
            settings,
            user.id,
            body.municipality_id,
            body.facility_id,
            body.values,
            [s.model_dump(exclude_none=True) for s in body.services],
            body.close,
            body.comment,
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _one(db, submission_id)


@router.post("/submissions/sync", status_code=status.HTTP_202_ACCEPTED)
def check_now(_: Editor, db: Db, settings: Config) -> dict[str, bool]:
    """Queue a sync with the hub now (the worker does it; nothing is called from here)."""
    queued = subs.queue_sync(db) if settings.hub_link_enabled else False
    db.commit()
    return {"queued": queued}


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: uuid.UUID, _: Editor, db: Db) -> SubmissionOut:
    """One submission: local validation report, changeset preview, status history."""
    return _one(db, submission_id)


@router.post("/submissions/{submission_id}/send", response_model=SubmissionOut)
def send(
    submission_id: uuid.UUID, body: SendIn, user: Editor, db: Db, settings: Config
) -> SubmissionOut:
    """Send a draft to the hub (queued for the worker)."""
    try:
        subs.send(db, settings, user.id, submission_id, body.confirm_close)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _one(db, submission_id)


@router.post("/submissions/{submission_id}/withdraw", response_model=SubmissionOut)
def withdraw(submission_id: uuid.UUID, user: Editor, db: Db, settings: Config) -> SubmissionOut:
    """Withdraw a submission (its submitter or an administrator), before the hub reviews it."""
    try:
        subs.withdraw(db, settings, user.id, user.is_admin, submission_id)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _one(db, submission_id)


@router.get(
    "/submissions/{submission_id}/export",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
def export(submission_id: uuid.UUID, user: Editor, db: Db, settings: Config) -> Response:
    """Download the offline submission file (for installations without a network path)."""
    try:
        content, name = subs.export_offline(db, settings, user.id, submission_id)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/hub-link", response_model=HubLinkOut)
def hub_link(_: Admin, db: Db, settings: Config) -> dict[str, Any]:
    """The hub connection and new package versions (administrators; never the token)."""
    return subs.hub_link(db, settings)


@router.get("/hub-link/pseudonyms", response_model=list[PseudonymOut])
def pseudonyms(_: Admin, db: Db) -> list[dict[str, Any]]:
    """Which user each pseudonymous id sent to the hub stands for (administrators only)."""
    return subs.pseudonyms(db)


@router.post(
    "/hub-link/downloads", response_model=DownloadOut, status_code=status.HTTP_202_ACCEPTED
)
def download(body: DownloadIn, admin: Admin, db: Db) -> DownloadOut:
    """Download a new package version from the hub (a job; then preview and confirm)."""
    try:
        download_id = subs.request_download(db, admin.id, body.version)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _download(db, download_id)


def _download(db: Session, download_id: uuid.UUID) -> DownloadOut:
    from sqlalchemy import text

    row = (
        db.execute(
            text(
                "SELECT d.id, d.version, d.status, d.staging_id, d.error, d.requested_at, "
                "u.username AS requested_by FROM hub_downloads d "
                "LEFT JOIN users u ON u.id = d.requested_by WHERE d.id = :i"
            ),
            {"i": download_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("submission.not_found", id=download_id))
    return DownloadOut(**dict(row))


@router.get("/hub-link/downloads/{download_id}", response_model=DownloadOut)
def download_status(download_id: uuid.UUID, _: Admin, db: Db) -> DownloadOut:
    """Status of a download."""
    return _download(db, download_id)


@router.get("/hub-link/downloads/{download_id}/preview", response_model=PreviewOut)
def download_preview(download_id: uuid.UUID, _: Admin, db: Db, settings: Config) -> PreviewOut:
    """Preview of a downloaded package (then confirm with the existing import)."""
    from solidaritynode_backend.routers.data import _preview
    from solidaritynode_backend.services.packages import PackageError, staged_path

    found = _download(db, download_id)
    if found.status != "done" or not found.staging_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, found.error or msg("submission.not_found", id=download_id)
        )
    try:
        path = staged_path(settings, found.staging_id)
    except PackageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return _preview(db, path, "hub", found.staging_id)

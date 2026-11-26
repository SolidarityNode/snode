"""API for municipal installations, in the hub (ADR 0014 Part A): mounted only in the hub.

Authenticated by the installation token (``Authorization: Bearer``), not by a session: the
municipal installation's worker calls it (ADR 0012: the installation opens every connection).
A token reaches only its own installation's submissions and its own study area's packages, and
submits only for the study area's core municipalities.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.schemas.hub import (
    InstallationInfoOut,
    SubmissionIn,
    SubmissionStatusOut,
)
from solidaritynode_backend.services.hub import installations, submissions
from solidaritynode_backend.services.hub.common import HubError
from solidaritynode_backend.services.hub.publish import package_archive
from solidaritynode_backend.services.throttle import client_address

router = APIRouter(prefix="/hub/installation", tags=["hub installation API"])

Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


def _fail(exc: HubError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


def installation(request: Request, db: Db, settings: Config) -> dict[str, Any]:
    """The installation of the bearer token (401 otherwise), with its contact recorded."""
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    address = client_address(
        request.client.host if request.client else None,
        request.headers.get("x-real-ip"),
        request.headers.get("x-forwarded-for"),
        settings.trusted_networks(),
    )
    try:
        inst = installations.authenticate(db, token, address)
    except HubError as exc:
        raise HTTPException(exc.status, str(exc), headers={"WWW-Authenticate": "Bearer"}) from None
    db.commit()
    return inst


Inst = Annotated[dict[str, Any], Depends(installation)]


@router.get("/me", response_model=InstallationInfoOut)
def me(inst: Inst, db: Db) -> dict[str, Any]:
    """The installation, its study area and its published packages."""
    return submissions.installation_packages(db, inst)


@router.post("/submissions", response_model=SubmissionStatusOut)
def submit(body: SubmissionIn, inst: Inst, db: Db, settings: Config) -> dict[str, Any]:
    """Receive a submission (idempotent by its id); the hub validates it again."""
    try:
        result = submissions.receive(db, settings, inst, body.model_dump(mode="json"))
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return result


@router.get("/submissions", response_model=list[SubmissionStatusOut])
def submission_statuses(
    inst: Inst, db: Db, ids: Annotated[list[uuid.UUID], Query(max_length=500)]
) -> list[dict[str, Any]]:
    """Status of the installation's own submissions (unknown or others' ids are left out)."""
    return submissions.statuses(db, inst, ids)


@router.post("/submissions/{submission_id}/withdraw", response_model=SubmissionStatusOut)
def withdraw(submission_id: uuid.UUID, inst: Inst, db: Db) -> dict[str, Any]:
    """Withdraw a submission before the hub starts reviewing it."""
    try:
        result = submissions.withdraw(db, inst, submission_id)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return result


@router.get(
    "/packages/{version}/download",
    response_class=FileResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download(version: str, inst: Inst, db: Db, settings: Config) -> FileResponse:
    """Download a published package of the installation's own study area."""
    try:
        path = package_archive(db, settings, str(inst["study_area_id"]), version)
    except HubError as exc:
        raise _fail(exc) from None
    return FileResponse(path, media_type="application/zip", filename=path.name)

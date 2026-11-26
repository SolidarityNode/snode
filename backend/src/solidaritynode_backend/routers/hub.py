"""Hub router (ADR 0012): mounted only when ``DEPLOYMENT_MODE=hub``.

In a municipal installation this router is not mounted, so every ``/hub`` path answers 404.

Roles in the hub (ADR 0012, 0015): **viewers** read everything (sources, onboarding, coverage,
facilities and their history, study areas, packages); **analysts** also upload facility files
and propose manual edits (pending changesets); **administrators** also register sources, run
the base step, change onboarding status, approve or reject changesets, create study areas and
publish packages. Long work (base step, package assembly) runs in the worker; these handlers
only queue it.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import CurrentUser, Principal, require_role
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.jobs import PostgresJobRunner
from solidaritynode_backend.messages import msg
from solidaritynode_backend.orm import Job
from solidaritynode_backend.schemas.api import RoleFeatureOut
from solidaritynode_backend.schemas.hub import (
    ApproveIn,
    ChangesetOut,
    ChangesetSummaryOut,
    CoverageRowOut,
    FacilityEditIn,
    FacilityOut,
    HistoryEntryOut,
    InstallationIn,
    InstallationOut,
    JobOut,
    OnboardingDetailOut,
    PublishIn,
    PublishOut,
    RecordOut,
    RejectIn,
    SourceOut,
    StartedOut,
    StatusIn,
    StudyAreaIn,
    StudyAreaOut,
    TokenOut,
)
from solidaritynode_backend.services.hub import facilities as fac
from solidaritynode_backend.services.hub import installations as hub_installations
from solidaritynode_backend.services.hub import submissions as hub_submissions
from solidaritynode_backend.services.hub.base import start_base
from solidaritynode_backend.services.hub.common import HubError, manual_transition
from solidaritynode_backend.services.hub.coverage import coverage_matrix
from solidaritynode_backend.services.hub.publish import (
    create_study_area,
    list_study_areas,
    package_archive,
    start_publish,
)
from solidaritynode_backend.services.hub.sources import (
    SourceMeta,
    list_sources,
    register_source,
)

router = APIRouter(prefix="/hub", tags=["hub"])

Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]
Admin = Annotated[Principal, Depends(require_role("admin"))]
Editor = Annotated[Principal, Depends(require_role("admin", "analyst"))]
CHUNK = 1024 * 1024


def _fail(exc: HubError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.get("/status", response_model=RoleFeatureOut)
def hub_status(user: CurrentUser) -> RoleFeatureOut:
    """What the hub offers in this version."""
    return RoleFeatureOut(
        role="hub",
        feature="onboarding",
        implemented=True,
        note="Raw sources, onboarding, facility imports, coverage and package publishing.",
    )


# --- Sources -------------------------------------------------------------------------------


@router.get("/sources", response_model=list[SourceOut])
def sources(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    """List registered raw sources, newest first."""
    return list_sources(db)


@router.post(
    "/sources",
    response_model=SourceOut,
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
async def register(
    request: Request,
    admin: Admin,
    db: Db,
    settings: Config,
    response: Response,
    file_name: Annotated[str, Query(min_length=1)],
    name: Annotated[str, Query(min_length=1)],
    layer_type: Annotated[str, Query()],
    version: Annotated[str, Query(min_length=1)],
    licence: Annotated[str, Query(min_length=1)],
    attribution: Annotated[str, Query(min_length=1)],
    processing_note: Annotated[str, Query()],
    coverage: Annotated[str, Query()] = "national",
    quality: Annotated[str, Query()] = "open_data",
    synthetic: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Register a raw source: the request body is the file, streamed to disk (no processing)."""
    meta = SourceMeta(
        name,
        layer_type,
        coverage,
        version,
        licence,
        attribution,
        processing_note,
        quality,
        synthetic,
    )
    limit = int(settings.hub_max_source_mb * 1024 * 1024)
    staging = settings.hub_storage_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"upload-{uuid.uuid4().hex}"
    size = 0
    try:
        with path.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise _fail(HubError("hub.source.too_large", status=413, limit=limit // 2**20))
                out.write(chunk)

        def work() -> tuple[dict[str, Any], bool]:
            with path.open("rb") as handle:
                return register_source(db, settings, handle, file_name, meta, admin.id)

        try:
            row, created = await run_in_threadpool(work)
        except HubError as exc:
            db.rollback()
            raise _fail(exc) from None
        db.commit()
    finally:
        path.unlink(missing_ok=True)
    if not created:
        response.status_code = status.HTTP_200_OK
    return {**row, "created": created}


# --- Onboarding and coverage ---------------------------------------------------------------


def _job(db: Session, job_id: object) -> JobOut | None:
    if job_id is None:
        return None
    job = db.get(Job, uuid.UUID(str(job_id)))
    if job is None:
        return None
    return JobOut(
        id=str(job.id),
        kind=job.kind,
        status=job.status,
        progress=job.progress,
        error=job.error,
        cancel_requested=job.cancel_requested,
    )


@router.get("/coverage", response_model=list[CoverageRowOut])
def coverage(
    _: CurrentUser,
    db: Db,
    settings: Config,
    onboarded: Annotated[
        bool | None, Query(description="true: onboarded only; false: others")
    ] = None,
) -> list[dict[str, Any]]:
    """Coverage matrix: municipalities × layers with onboarding status (the onboarding list)."""
    return coverage_matrix(db, settings, onboarded)


def _records(db: Session, where: str, params: dict[str, Any]) -> list[RecordOut]:
    rows = db.execute(
        text(
            "SELECT r.*, u.username AS created_by_name FROM hub_processing_records r "
            f"LEFT JOIN users u ON u.id = r.created_by WHERE {where} ORDER BY r.id DESC"
        ),
        params,
    ).mappings()
    return [RecordOut(**{**dict(r), "job": _job(db, r["job_id"])}) for r in rows]


@router.get("/onboarding/{municipality_id}", response_model=OnboardingDetailOut)
def onboarding_detail(
    municipality_id: str, _: CurrentUser, db: Db, settings: Config
) -> OnboardingDetailOut:
    """One municipality: status with history, base-step reports and job, facility counts."""
    row = next(
        (r for r in coverage_matrix(db, settings) if r["municipality_id"] == municipality_id),
        None,
    )
    if row is None:
        raise _fail(
            HubError("hub.error.municipality_unknown", status=404, municipality=municipality_id)
        )
    events = [
        dict(e)
        for e in db.execute(
            text(
                "SELECT e.from_status, e.to_status, u.username AS by, e.at, e.note "
                "FROM hub_onboarding_events e LEFT JOIN users u ON u.id = e.by_user "
                "WHERE e.municipality_id = :m ORDER BY e.id"
            ),
            {"m": municipality_id},
        ).mappings()
    ]
    job_id = db.execute(
        text("SELECT last_job_id FROM hub_onboarding WHERE municipality_id = :m"),
        {"m": municipality_id},
    ).scalar_one_or_none()
    counts = db.execute(
        text(
            "SELECT count(*) FILTER (WHERE valid_to IS NULL), count(*) FILTER (WHERE valid_to IS "
            "NOT NULL) FROM hub_features WHERE layer = 'facilities' AND municipality_id = :m"
        ),
        {"m": municipality_id},
    ).one()
    return OnboardingDetailOut(
        municipality_id=municipality_id,
        name=row["name"],
        status=row["status"],
        layers=row["layers"],
        events=events,
        records=_records(
            db, "r.municipality_id = :m AND r.kind <> 'package_publish'", {"m": municipality_id}
        ),
        job=_job(db, job_id),
        facilities_open=int(counts[0]),
        facilities_closed=int(counts[1]),
    )


@router.post(
    "/onboarding/{municipality_id}/base",
    response_model=StartedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def onboard_base(municipality_id: str, admin: Admin, db: Db, settings: Config) -> StartedOut:
    """Queue the base step (clip, ids, checks) for a municipality and its buffer."""
    try:
        record_id, job_id = start_base(
            db, settings, PostgresJobRunner(db), municipality_id, admin.id
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return StartedOut(record_id=record_id, job_id=job_id)


@router.post("/onboarding/{municipality_id}/status", response_model=OnboardingDetailOut)
def change_status(
    municipality_id: str, body: StatusIn, admin: Admin, db: Db, settings: Config
) -> OnboardingDetailOut:
    """Change the onboarding status by hand (for example ready for review)."""
    try:
        manual_transition(db, municipality_id, body.status, admin.id)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return onboarding_detail(municipality_id, admin, db, settings)


@router.get("/records/{record_id}", response_model=RecordOut)
def record(record_id: int, _: CurrentUser, db: Db) -> RecordOut:
    """One processing record (inputs, parameters, outputs, checks)."""
    found = _records(db, "r.id = :i", {"i": record_id})
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("hub.error.job_not_found"))
    return found[0]


@router.get("/jobs/{job_id}", response_model=JobOut)
def job(job_id: uuid.UUID, _: CurrentUser, db: Db) -> JobOut:
    """Progress of a hub job."""
    found = _job(db, job_id)
    if found is None or found.kind not in ("hub_onboard_base", "hub_publish"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("hub.error.job_not_found"))
    return found


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, _: Admin, db: Db) -> JobOut:
    """Cancel a queued hub job, or stop a running one at its next step (nothing is stored)."""
    found = _job(db, job_id)
    if found is None or found.kind not in ("hub_onboard_base", "hub_publish"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("hub.error.job_not_found"))
    PostgresJobRunner(db).cancel(str(job_id))
    db.commit()
    result = _job(db, job_id)
    assert result is not None
    return result


# --- Facilities ----------------------------------------------------------------------------

_MEDIA = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "gpkg": "application/geopackage+sqlite3",
}


def _download(content: bytes, media: str, name: str) -> Response:
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(
    "/facilities/template",
    response_class=Response,
    responses={200: {"content": {m: {} for m in _MEDIA.values()}}},
)
def facility_template(
    _: CurrentUser, settings: Config, format: Literal["csv", "xlsx", "gpkg"] = "xlsx"
) -> Response:
    """Download the facility import template (XLSX with instructions in Greek and English)."""
    return _download(*fac.template_file(settings, format))


@router.get(
    "/facilities/export",
    response_class=Response,
    responses={200: {"content": {_MEDIA["csv"]: {}, _MEDIA["xlsx"]: {}}}},
)
def facility_export(
    _: CurrentUser,
    db: Db,
    municipality: str,
    format: Literal["csv", "xlsx"] = "xlsx",
) -> Response:
    """Download the open facilities of a municipality in the template, to extend them."""
    return _download(*fac.facilities_export(db, municipality, format))


@router.get("/facilities", response_model=list[FacilityOut])
def facilities(_: CurrentUser, db: Db, municipality: str | None = None) -> list[dict[str, Any]]:
    """List curated facilities (open and closed)."""
    return fac.list_facilities(db, municipality)


@router.get("/facilities/{facility_id}/history", response_model=list[HistoryEntryOut])
def facility_history(facility_id: str, _: CurrentUser, db: Db) -> list[dict[str, Any]]:
    """Every approved change of a facility, with author, date, source and comment."""
    try:
        return fac.facility_history(db, facility_id)
    except HubError as exc:
        raise _fail(exc) from None


def _changeset(db: Session, changeset_id: int) -> ChangesetOut:
    try:
        return ChangesetOut(**fac.changeset_detail(db, changeset_id))
    except HubError as exc:
        raise _fail(exc) from None


@router.post(
    "/facility-imports",
    response_model=ChangesetOut,
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
async def facility_import(
    request: Request,
    user: Editor,
    db: Db,
    settings: Config,
    municipality: Annotated[str, Query(min_length=1)],
    file_name: Annotated[str, Query(min_length=1)],
    source: Annotated[str, Query(min_length=1)],
    comment: str = "",
    licence: str = "CC-BY-4.0",
    attribution: str = "",
    complete_list: bool = False,
    is_correction: bool = False,
) -> ChangesetOut:
    """Upload a facility file (CSV, XLSX or GeoPackage): validation report and changeset preview.

    Nothing changes until an administrator approves the changeset.
    """
    limit = int(settings.hub_max_facility_file_mb * 1024 * 1024)
    if Path(file_name).suffix.lower() not in fac.EXTENSIONS:
        raise _fail(HubError("hub.import.unsupported_type", file=file_name))
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise _fail(
                HubError(
                    "hub.source.too_large", status=413, limit=settings.hub_max_facility_file_mb
                )
            )
    req = fac.ImportRequest(
        municipality, source, comment, licence, attribution, complete_list, is_correction
    )
    try:
        changeset_id = await run_in_threadpool(
            fac.create_import, db, settings, req, file_name, bytes(data), user.id
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _changeset(db, changeset_id)


@router.post("/facilities/edits", response_model=ChangesetOut, status_code=status.HTTP_201_CREATED)
def facility_edit(body: FacilityEditIn, user: Editor, db: Db, settings: Config) -> ChangesetOut:
    """Add, update or close one facility through the form (a pending changeset)."""
    try:
        changeset_id = fac.manual_changeset(
            db,
            settings,
            body.municipality_id,
            body.facility_id,
            body.values,
            [s.model_dump(exclude_none=True) for s in body.services],
            body.close,
            body.comment,
            user.id,
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _changeset(db, changeset_id)


@router.get("/changesets", response_model=list[ChangesetSummaryOut])
def changesets(_: CurrentUser, db: Db, municipality: str | None = None) -> list[dict[str, Any]]:
    """List changesets, newest first."""
    return fac.list_changesets(db, municipality)


@router.get("/changesets/{changeset_id}", response_model=ChangesetOut)
def changeset(changeset_id: int, _: CurrentUser, db: Db) -> ChangesetOut:
    """One changeset: validation report and preview of the changes."""
    return _changeset(db, changeset_id)


@router.get(
    "/changesets/{changeset_id}/report",
    response_class=Response,
    responses={200: {"content": {_MEDIA["csv"]: {}, _MEDIA["xlsx"]: {}}}},
)
def changeset_report(
    changeset_id: int, _: CurrentUser, db: Db, format: Literal["csv", "xlsx"] = "csv"
) -> Response:
    """Download the validation report (spreadsheet formulas escaped)."""
    try:
        return _download(*fac.report_export(db, changeset_id, format))
    except HubError as exc:
        raise _fail(exc) from None


@router.post("/changesets/{changeset_id}/approve", response_model=ChangesetOut)
def approve(
    changeset_id: int, body: ApproveIn, admin: Admin, db: Db, settings: Config
) -> ChangesetOut:
    """Apply a changeset (administrators); a complete list needs the number to close."""
    try:
        fac.approve_changeset(
            db,
            settings,
            changeset_id,
            admin.id,
            body.comment,
            body.confirm_close,
            body.resolutions,
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _changeset(db, changeset_id)


@router.post("/changesets/{changeset_id}/reject", response_model=ChangesetOut)
def reject(changeset_id: int, body: RejectIn, admin: Admin, db: Db) -> ChangesetOut:
    """Reject a changeset (it stays in the history; nothing is applied)."""
    try:
        fac.reject_changeset(db, changeset_id, admin.id, body.comment)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _changeset(db, changeset_id)


@router.post("/changesets/{changeset_id}/review", response_model=ChangesetOut)
def start_review(changeset_id: int, admin: Admin, db: Db) -> ChangesetOut:
    """Record that an administrator started reviewing a municipal submission.

    From then on the municipality can no longer withdraw it (ADR 0014 A4).
    """
    current = _changeset(db, changeset_id)
    hub_submissions.start_review(db, current.id, admin.id)
    db.commit()
    return _changeset(db, changeset_id)


@router.post(
    "/submission-files",
    response_model=ChangesetOut,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            "required": True,
        }
    },
)
async def upload_submission_file(
    request: Request, _: Admin, db: Db, settings: Config
) -> ChangesetOut:
    """Upload an offline submission file exported by a municipal installation (ADR 0014 A3)."""
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

    def work() -> int:
        inst, payload = hub_submissions.verify_offline_file(db, bytes(data))
        result = hub_submissions.receive(db, settings, inst, payload, offline=True)
        return int(result["changeset_id"])

    try:
        changeset_id = await run_in_threadpool(work)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return _changeset(db, changeset_id)


# --- Installations (ADR 0014 Part A) ---------------------------------------------------------


@router.get("/installations", response_model=list[InstallationOut])
def list_installations(_: Admin, db: Db) -> list[dict[str, Any]]:
    """Registered municipal installations (tokens are never shown again)."""
    return hub_installations.list_installations(db)


@router.post("/installations", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register_installation(body: InstallationIn, admin: Admin, db: Db) -> dict[str, Any]:
    """Register an installation for one study area and issue its token (shown once)."""
    try:
        row, token = hub_installations.register_installation(
            db, body.name, body.study_area_id, admin.id
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return {"installation": row, "token": token}


@router.post("/installations/{installation_id}/token", response_model=TokenOut)
def issue_token(installation_id: uuid.UUID, _: Admin, db: Db) -> dict[str, Any]:
    """Issue a new token (shown once); the previous one stops working at once."""
    try:
        token = hub_installations.issue_token(db, installation_id)
        row = hub_installations.get_installation(db, installation_id)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return {"installation": row, "token": token}


@router.post("/installations/{installation_id}/revoke", response_model=InstallationOut)
def revoke_token(installation_id: uuid.UUID, _: Admin, db: Db) -> dict[str, Any]:
    """Revoke the installation's token at once."""
    try:
        hub_installations.revoke(db, installation_id)
        row = hub_installations.get_installation(db, installation_id)
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return row


# --- Study areas and packages --------------------------------------------------------------


@router.get("/study-areas", response_model=list[StudyAreaOut])
def study_areas(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    """Study areas with their packages; ``update_available`` is the propagation list."""
    return [
        {
            **a,
            "pending": a["pending"],
            "packages": [
                {**p, "job_id": str(p["job_id"]) if p["job_id"] else None} for p in a["packages"]
            ],
        }
        for a in list_study_areas(db)
    ]


@router.post("/study-areas", response_model=StudyAreaOut, status_code=status.HTTP_201_CREATED)
def new_study_area(body: StudyAreaIn, admin: Admin, db: Db, settings: Config) -> dict[str, Any]:
    """Register the study area of an installation."""
    try:
        create_study_area(
            db,
            settings,
            body.id,
            body.name,
            body.core_municipalities,
            body.buffer_rule,
            body.buffer_distance_m,
            admin.id,
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return next(a for a in study_areas(admin, db) if a["id"] == body.id)


@router.post(
    "/study-areas/{study_area_id}/publish",
    response_model=PublishOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def publish(
    study_area_id: str, body: PublishIn, admin: Admin, db: Db, settings: Config
) -> dict[str, Any]:
    """Queue the next package version of a study area (a deliberate action)."""
    try:
        started = start_publish(
            db, settings, PostgresJobRunner(db), study_area_id, body.comment, admin.id
        )
    except HubError as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return started


@router.get(
    "/study-areas/{study_area_id}/packages/{version}/download",
    response_class=FileResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_package(
    study_area_id: str, version: str, _: CurrentUser, db: Db, settings: Config
) -> FileResponse:
    """Download a published package archive (import it on the installation's Admin screen)."""
    try:
        path = package_archive(db, settings, study_area_id, version)
    except HubError as exc:
        raise _fail(exc) from None
    return FileResponse(path, media_type="application/zip", filename=path.name)

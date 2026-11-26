"""Data versions, map layers and data package import (ADR 0013; admin for imports)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import CurrentUser, Principal, require_role
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.messages import msg
from solidaritynode_backend.orm import DataVersion
from solidaritynode_backend.schemas.api import (
    AvailablePackage,
    CatalogOut,
    CoverageOut,
    DataVersionOut,
    ImportIn,
    ImportOut,
    LayerLicenceOut,
    PreviewIn,
    PreviewOut,
    RevalidationOut,
    StorageOut,
)
from solidaritynode_backend.services.packages import (
    FEATURE_LAYERS,
    PackageError,
    activate_version,
    available_packages,
    available_path,
    import_package,
    opened_package,
    preview_package,
    read_package,
    stage_upload,
    staged_path,
)
from solidaritynode_backend.services.study_area import is_open
from solidaritynode_backend.services.submissions import mark_imported

router = APIRouter(tags=["data"])

Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]
Admin = Annotated[Principal, Depends(require_role("admin"))]

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def data_version_out(db: Session, dv: DataVersion) -> DataVersionOut:
    """Build the API view of a data version."""
    coverage = [
        CoverageOut(municipality_id=m, layer=layer, status=s, layer_version=v)
        for m, layer, s, v in db.execute(
            text(
                "SELECT municipality_id, layer, status, layer_version FROM data_coverage "
                "WHERE data_version_id = :dv ORDER BY municipality_id, layer"
            ),
            {"dv": dv.id},
        )
    ]
    warned = sorted(
        {
            r[0]
            for r in db.execute(
                text("SELECT unit_id FROM data_warnings WHERE data_version_id = :dv"),
                {"dv": dv.id},
            )
        }
    )
    m = dv.manifest
    return DataVersionOut(
        id=dv.id,
        package_id=dv.package_id,
        version=dv.version,
        schema_version=dv.schema_version,
        created=dv.created,
        active=dv.active,
        imported_at=dv.imported_at,
        synthetic=bool(m.get("synthetic", False)),
        study_area=m.get("study_area", {}),
        changelog=m.get("changelog", []),
        processing_notes=m.get("processing_notes", []),
        sources=m.get("sources", []),
        layer_licences=[
            LayerLicenceOut(
                layer=name,
                licence=str(e.get("licence", "")),
                attribution=str(e.get("attribution", "")),
            )
            for name, e in sorted(m.get("layers", {}).items())
        ],
        coverage=coverage,
        edge_effect_units=warned,
    )


def _get_dv(db: Session, data_version_id: int) -> DataVersion:
    dv = db.get(DataVersion, data_version_id)
    if dv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("error.data_version_not_found"))
    return dv


@router.get("/data-versions", response_model=list[DataVersionOut])
def list_data_versions(_: CurrentUser, db: Db) -> list[DataVersionOut]:
    """List imported data versions, newest first."""
    rows = db.scalars(select(DataVersion).order_by(DataVersion.imported_at.desc()))
    return [data_version_out(db, dv) for dv in rows]


@router.get(
    "/data-versions/active",
    response_model=DataVersionOut,
    responses={404: {"description": "No data package imported yet"}},
)
def active_data_version(_: CurrentUser, db: Db) -> DataVersionOut:
    """Return the active data version."""
    dv = db.scalar(select(DataVersion).where(DataVersion.active))
    if dv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("error.no_data"))
    return data_version_out(db, dv)


@router.get("/data-versions/{data_version_id}", response_model=DataVersionOut)
def get_data_version(data_version_id: int, _: CurrentUser, db: Db) -> DataVersionOut:
    """Return one data version."""
    return data_version_out(db, _get_dv(db, data_version_id))


@router.get("/data-versions/{data_version_id}/catalog", response_model=CatalogOut)
def catalog(data_version_id: int, _: CurrentUser, db: Db) -> CatalogOut:
    """Return the groups and services of a data version."""
    _get_dv(db, data_version_id)
    out: dict[str, list[dict[str, Any]]] = {"groups": [], "services": []}
    for table, props in db.execute(
        text(
            "SELECT table_name, properties FROM data_records WHERE data_version_id = :dv "
            "AND table_name IN ('groups', 'services') ORDER BY table_name, row_no"
        ),
        {"dv": data_version_id},
    ):
        out[table].append(
            {k: (v or None) if k == "max_acceptable_wait" else v for k, v in props.items()}
        )
    return CatalogOut.model_validate(out)


@router.get("/data-versions/{data_version_id}/layers/{layer}")
def layer_geojson(data_version_id: int, layer: str, _: CurrentUser, db: Db) -> dict[str, Any]:
    """Return one layer as GeoJSON in EPSG:4326 for the map.

    Every feature keeps its stable id and metadata (role, quality, valid_from/valid_to) plus
    ``closed``; spatial units also carry ``edge_effect_warning`` and its details (OQ-28).
    """
    if layer not in FEATURE_LAYERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg("error.unknown_layer", layer=layer))
    dv = _get_dv(db, data_version_id)
    warnings: dict[str, list[str]] = {}
    for unit, detail in db.execute(
        text("SELECT unit_id, detail FROM data_warnings WHERE data_version_id = :dv"),
        {"dv": dv.id},
    ):
        warnings.setdefault(unit, []).append(detail)
    features = []
    for fid, props, geometry in db.execute(
        text(
            "SELECT feature_id, properties, ST_AsGeoJSON(ST_Transform(geom, 4326), 7) "
            "FROM data_features WHERE data_version_id = :dv AND layer = :layer "
            "ORDER BY feature_id"
        ),
        {"dv": dv.id, "layer": layer},
    ):
        props = {k: v for k, v in props.items() if not k.startswith("_")}
        props["closed"] = not is_open(props, dv.created)
        if layer == "spatial_units":
            props["edge_effect_warning"] = fid in warnings
            props["edge_effect_details"] = warnings.get(fid, [])
        features.append(
            {"type": "Feature", "id": fid, "properties": props, "geometry": json.loads(geometry)}
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/storage", response_model=StorageOut)
def storage(_: Admin, db: Db, settings: Config) -> StorageOut:
    """Disk usage of the results volume: samples files and free space (ADR 0017).

    Nothing is deleted automatically in v0.1; this lets an administrator watch the volume.
    """
    runs_dir = settings.results_dir / "runs"
    files = [p for p in runs_dir.rglob("*.parquet") if p.is_file()] if runs_dir.exists() else []
    usage = shutil.disk_usage(settings.results_dir) if settings.results_dir.exists() else None
    return StorageOut(
        results_dir=str(settings.results_dir),
        runs_with_samples=int(
            db.scalar(text("SELECT count(*) FROM runs WHERE samples_path IS NOT NULL")) or 0
        ),
        samples_files=len(files),
        samples_bytes=sum(p.stat().st_size for p in files),
        total_bytes=usage.total if usage else None,
        free_bytes=usage.free if usage else None,
    )


@router.get("/packages/available", response_model=list[AvailablePackage])
def list_available(_: Admin, settings: Config) -> list[AvailablePackage]:
    """List packages offered for import from the server's package directory."""
    return [AvailablePackage(**p) for p in available_packages(settings)]


def _preview(db: Session, path: Path, source: str, staging_id: str | None) -> PreviewOut:
    try:
        with opened_package(path) as directory:
            content = read_package(directory)
    except PackageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    preview = preview_package(db, content)
    return PreviewOut(staging_id=staging_id, source=source, **preview)


@router.post("/packages/preview", response_model=PreviewOut)
def preview_available(body: PreviewIn, _: Admin, db: Db, settings: Config) -> PreviewOut:
    """Validate a server package and preview its changes against the active version."""
    try:
        path = available_path(settings, body.name)
    except PackageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return _preview(db, path, body.name, None)


@router.post(
    "/packages/upload",
    response_model=PreviewOut,
    openapi_extra={
        "requestBody": {
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            "required": True,
        }
    },
)
async def preview_upload(request: Request, _: Admin, db: Db, settings: Config) -> PreviewOut:
    """Upload a package archive (``.zip`` or ``.tar.gz`` body), validate it and preview it."""
    data = await request.body()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg("error.empty_upload"))
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, msg("error.upload_too_large"))
    staging_id = stage_upload(settings, data)
    path = staged_path(settings, staging_id)
    return await run_in_threadpool(_preview, db, path, "upload", staging_id)


@router.post("/packages/import", response_model=ImportOut)
def confirm_import(body: ImportIn, admin: Admin, db: Db, settings: Config) -> ImportOut:
    """Import a previewed package in one transaction and make it the active data version."""
    try:
        if body.name:
            path = available_path(settings, body.name)
        elif body.staging_id:
            path = staged_path(settings, body.staging_id)
        else:
            raise PackageError("give a package name or a staging id")
        with opened_package(path) as directory:
            content = read_package(directory)
        outcome = import_package(db, settings, content, admin.id)
        mark_imported(db)  # submissions published in this version (ADR 0014 Part A)
    except PackageError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    db.commit()
    return ImportOut(
        data_version_id=outcome.data_version_id,
        noop=outcome.noop,
        baseline_run_id=outcome.baseline_run_id,
        revalidation=[RevalidationOut(**r) for r in outcome.revalidation],
    )


@router.post(
    "/data-versions/{data_version_id}/activate",
    response_model=ImportOut,
    responses={409: {"description": "The data version is already active"}},
)
def activate_data_version(
    data_version_id: int, admin: Admin, db: Db, settings: Config
) -> ImportOut:
    """Make an earlier imported data version active again (rollback).

    Like an import, this queues a baseline run on that data and revalidates every scenario.
    """
    try:
        outcome = activate_version(db, settings, data_version_id, admin.id)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, msg("error.data_version_not_found")
        ) from None
    except PackageError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    db.commit()
    return ImportOut(
        data_version_id=outcome.data_version_id,
        noop=False,
        baseline_run_id=outcome.baseline_run_id,
        revalidation=[RevalidationOut(**r) for r in outcome.revalidation],
    )

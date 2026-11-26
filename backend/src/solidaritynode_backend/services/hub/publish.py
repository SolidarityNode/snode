"""Study areas, package publishing and propagation of updates (ADR 0013; DP-006).

A **study area** is registered in the hub for each installation: one or more core
municipalities and a buffer rule (``whole_neighbouring_municipalities`` or ``distance``; the
buffer definition is open, OQ-28). Publishing a package for it is a background job that:

1. selects the core and buffer municipalities, their spatial units, network nodes inside those
   units (plus the nodes their units and facilities point to) and edges with both ends kept, and
   their facilities, **valid at the publish date** plus every feature an earlier version of the
   package had (closed features keep their ``valid_to``; a package never drops a feature, so
   the installation's import accepts it);
2. writes the package in the format of ADR 0013 (one GeoPackage ``layers.gpkg`` in the hub CRS,
   CSV tables, ``manifest.json`` with checksums, coverage of every municipality and layer,
   licences, sources, provenance and changelog), schema ``2.1``;
3. reads the result back with the installation's own validator
   (:func:`solidaritynode_backend.services.packages.read_package`), so a published package
   always imports;
4. stores it immutably (a database trigger refuses changes to a published row) as a directory
   and a ``.zip`` archive.

**Version**: ``1.0.0`` first; then **minor** when the changes since the previous version add,
close or update features, **patch** when they are only corrections (changesets marked as
corrections), **major** only for a schema change of the package format.

**Propagation**: every approved changeset and base step records the municipalities it changed.
A study area whose core or buffer contains one of them, changed after its last published
version, is listed as **update available** with a draft changelog. Publishing is always a
deliberate action.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.gpkg import Srs, blob_from_wkb, write_geopackage
from solidaritynode_backend.jobs import JobCancelledError, JobContext, JobRunner
from solidaritynode_backend.messages import msg
from solidaritynode_backend.services.hub.common import (
    BASE_NOTE,
    COVERAGE_LAYERS,
    FACILITY_NOTE,
    PUBLISH_NOTE,
    HubError,
    add_record,
    check,
    finish_record,
    jsonb,
    set_status,
)
from solidaritynode_backend.services.hub.coverage import municipality_coverage
from solidaritynode_backend.services.hub.sources import latest_sources, source_input, source_path
from solidaritynode_backend.services.packages import (
    PackageError,
    archive_directory,
    read_package,
)

__all__ = [
    "PUBLISH_JOB_KIND",
    "SCHEMA_VERSION",
    "create_study_area",
    "list_study_areas",
    "package_archive",
    "pending_changes",
    "run_publish",
    "start_publish",
    "study_area_municipalities",
]

PUBLISH_JOB_KIND = "hub_publish"
SCHEMA_VERSION = "2.1"
"""Package schema written by the hub: 2.0 plus optional manifest keys (``provenance``, the
``spatial_units`` and ``susceptibility`` coverage layers). Installations read any 2.x."""
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_META = (
    ("municipality_id", "TEXT"),
    ("role", "TEXT"),
    ("quality", "TEXT"),
    ("valid_from", "DATE"),
    ("valid_to", "DATE"),
    ("processing_note", "TEXT"),
)
LAYER_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "municipalities": (("name", "TEXT"),),
    "spatial_units": (("unit_id", "TEXT"), ("name", "TEXT"), ("centroid_node_id", "TEXT")),
    "facilities": (
        ("facility_id", "TEXT"),
        ("name", "TEXT"),
        ("facility_type", "TEXT"),
        ("node_id", "TEXT"),
        ("unit_id", "TEXT"),
        ("external_id", "TEXT"),
        ("address", "TEXT"),
        ("operating_hours", "TEXT"),
        ("public_phone", "TEXT"),
        ("public_email", "TEXT"),
        ("source", "TEXT"),
        ("status", "TEXT"),
        ("notes", "TEXT"),
    ),
    "network_nodes": (("node_id", "TEXT"), ("kind", "TEXT"), ("unit_id", "TEXT")),
    "network_edges": (
        ("edge_id", "TEXT"),
        ("from_node_id", "TEXT"),
        ("to_node_id", "TEXT"),
        ("length_m", "REAL"),
        ("travel_time_walk_min", "REAL"),
        ("travel_time_car_min", "REAL"),
        ("closable", "BOOLEAN"),
    ),
}
_SOURCE_OF_LAYER = {
    "municipalities": "boundaries",
    "spatial_units": "spatial_units",
    "network_nodes": "network",
    "network_edges": "network",
}


# --- Study areas -----------------------------------------------------------------------------


def create_study_area(
    db: Session,
    settings: Settings,
    study_area_id: str,
    name: str,
    core: Sequence[str],
    buffer_rule: str | None,
    buffer_distance_m: float | None,
    user_id: int | None,
) -> None:
    """Register a study area (core municipalities and buffer rule) for an installation.

    Raises:
        HubError: On an invalid id, an existing id, or a core municipality without base data.
    """
    if not _ID.match(study_area_id):
        raise HubError("hub.study_area.bad_id", id=study_area_id)
    rule = buffer_rule or settings.hub_buffer_rule
    if rule not in ("whole_neighbouring_municipalities", "distance"):
        raise HubError("hub.study_area.bad_rule", rule=rule)
    distance = (buffer_distance_m or settings.hub_buffer_distance_m) if rule == "distance" else None
    if not core:
        raise HubError("hub.source.field_required", field="core_municipalities")
    for mun in core:
        ready = db.execute(
            text("SELECT status FROM hub_onboarding WHERE municipality_id = :m"), {"m": mun}
        ).scalar_one_or_none()
        if ready in (None, "not_started"):
            raise HubError("hub.error.not_onboarded", municipality=mun)
    exists = db.execute(
        text("SELECT 1 FROM hub_study_areas WHERE id = :i"), {"i": study_area_id}
    ).first()
    if exists:
        raise HubError("hub.error.study_area_exists", status=409, id=study_area_id)
    db.execute(
        text(
            "INSERT INTO hub_study_areas (id, name, core_municipalities, buffer_rule, "
            "buffer_distance_m, created_by) VALUES (:i, :n, :c, :r, :d, :u)"
        ),
        {
            "i": study_area_id,
            "n": name,
            "c": sorted(set(core)),
            "r": rule,
            "d": distance,
            "u": user_id,
        },
    )


def _study_area(db: Session, study_area_id: str) -> dict[str, Any]:
    row = (
        db.execute(text("SELECT * FROM hub_study_areas WHERE id = :i"), {"i": study_area_id})
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("hub.error.study_area_not_found", status=404, id=study_area_id)
    return dict(row)


def study_area_municipalities(db: Session, area: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Return ``(core, buffer)`` municipality ids of a study area, from the curated boundaries."""
    core = sorted(area["core_municipalities"])
    if area["buffer_rule"] == "distance":
        sql = (
            "SELECT DISTINCT u.municipality_id FROM hub_features u, hub_features c "
            "WHERE u.layer = 'spatial_units' AND c.layer = 'municipalities' "
            "AND c.feature_id = ANY(:core) AND u.valid_to IS NULL "
            "AND ST_DWithin(u.geom, c.geom, :d)"
        )
    else:
        sql = (
            "SELECT DISTINCT m.feature_id FROM hub_features m, hub_features c "
            "WHERE m.layer = 'municipalities' AND c.layer = 'municipalities' "
            "AND c.feature_id = ANY(:core) AND m.valid_to IS NULL AND ST_Intersects(m.geom, c.geom)"
        )
    found = {
        str(r[0])
        for r in db.execute(text(sql), {"core": core, "d": area.get("buffer_distance_m") or 0})
    }
    return core, sorted(found - set(core))


# --- Changes since the last version ------------------------------------------------------------


def _last_package(db: Session, study_area_id: str) -> dict[str, Any] | None:
    row = (
        db.execute(
            text(
                "SELECT * FROM hub_packages WHERE study_area_id = :s AND status = 'published' "
                "ORDER BY published_at DESC, id DESC LIMIT 1"
            ),
            {"s": study_area_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


def _fingerprint(f: Mapping[str, Any], core: Sequence[str]) -> str:
    """Hash everything a package records about a feature (geometry, metadata, properties)."""
    props = {k: v for k, v in dict(f["properties"]).items() if not k.startswith("_")}
    payload = json.dumps(
        [
            f["municipality_id"],
            "core" if f["municipality_id"] in core else "buffer",
            f["quality"],
            f["processing_note"],
            f["valid_from"].isoformat(),
            f["valid_to"].isoformat() if f["valid_to"] else None,
            props,
        ],
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode() + bytes(f["wkb"])).hexdigest()


def pending_changes(
    db: Session, study_area_id: str, until_record: int | None = None
) -> dict[str, Any]:
    """Return what the next package of a study area would change against the last one.

    The next package's features are selected as if publishing today and compared, feature by
    feature (a hash of geometry, metadata and properties), with those of the last published
    version; coverage statuses are compared too. So only changes that reach this study area's
    package count: a neighbour's onboarding that adds features outside it does not.

    Returns:
        ``features`` (per layer: ``added``, ``changed``, ``closed`` ids), ``coverage``
        (changed statuses), ``records`` (base steps and approved changesets behind them),
        ``changelog`` (a draft), ``bump`` (``initial``, ``minor`` or ``patch``),
        ``next_version``, ``last`` (the last published version) and ``changed``.
    """
    area = _study_area(db, study_area_id)
    core, buffer = study_area_municipalities(db, area)
    last = _last_package(db, study_area_id)
    since = int(last["manifest"]["provenance_until_record"]) if last else 0
    before: dict[str, dict[str, str]] = dict(last["feature_ids"]) if last else {}
    today = datetime.now(UTC).date()
    now = _features(db, area, core, buffer, today, {k: list(v) for k, v in before.items()})
    features: dict[str, dict[str, list[str]]] = {}
    for layer, rows in now.items():
        old = before.get(layer, {})
        entry: dict[str, list[str]] = {"added": [], "changed": [], "closed": []}
        for f in rows:
            fid = str(f["feature_id"])
            fp = _fingerprint(f, core)
            if fid not in old:
                entry["added"].append(fid)
            elif old[fid] != fp:
                entry["closed" if f["valid_to"] is not None else "changed"].append(fid)
        if any(entry.values()):
            features[layer] = entry
    coverage = []
    if last is not None:
        current = municipality_coverage(db, [*core, *buffer])
        previous = last["manifest"].get("coverage", {})
        for mun in sorted(current):
            for layer, cov in current[mun].items():
                was = previous.get(mun, {}).get(layer, {}).get("status")
                if was != cov["status"]:
                    coverage.append(
                        {
                            "municipality_id": mun,
                            "layer": layer,
                            "before": was,
                            "after": cov["status"],
                        }
                    )
    records = [
        dict(r)
        for r in db.execute(
            text(
                "SELECT r.id, r.kind, r.municipality_id, r.summary, r.finished_at, "
                "r.affected_municipalities, r.outputs, c.is_correction "
                "FROM hub_processing_records r LEFT JOIN hub_changesets c ON c.record_id = r.id "
                "WHERE r.kind IN ('onboarding_base', 'facility_changeset') "
                "AND r.status = 'succeeded' AND r.changed AND r.id > :since "
                "AND (CAST(:until AS integer) IS NULL OR r.id <= :until) "
                "AND r.affected_municipalities && :area ORDER BY r.id"
            ),
            {"since": since, "until": until_record, "area": [*core, *buffer]},
        ).mappings()
    ]
    # A base step counts only if it touched a feature of this package (a neighbour's onboarding
    # also adds features around the neighbour that never enter this study area).
    in_package = {str(f["feature_id"]) for rows in now.values() for f in rows}

    def touches(record: Mapping[str, Any]) -> bool:
        if record["kind"] != "onboarding_base":
            return True
        layers = (record.get("outputs") or {}).get("layers", {})
        return any(
            fid in in_package
            for entry in layers.values()
            for key in ("added", "changed", "closed")
            for fid in entry.get(key, [])
        )

    records = [r for r in records if touches(r)]
    for r in records:
        r.pop("outputs", None)
    changed = last is None or bool(features) or bool(coverage)
    if last is None:
        bump, version = "initial", "1.0.0"
    else:
        major, minor, patch = (int(x) for x in str(last["version"]).split("."))
        only_updates = all(not v["added"] and not v["closed"] for v in features.values())
        corrections = bool(records) and all(r["is_correction"] for r in records)
        bump = "patch" if only_updates and corrections and not coverage else "minor"
        version = f"{major}.{minor}.{patch + 1}" if bump == "patch" else f"{major}.{minor + 1}.0"
    lines = []
    if last is not None:
        for layer, entry in sorted(features.items()):
            for kind in ("added", "changed", "closed"):
                if entry[kind]:
                    shown = ", ".join(entry[kind][:10]) + (" …" if len(entry[kind]) > 10 else "")
                    lines.append(f"{layer} {kind}: {shown}")
        lines += [
            f"coverage {c['municipality_id']}/{c['layer']}: "
            f"{c['before'] or 'missing'} -> {c['after']}"
            for c in coverage
        ]
    lines += [str(r["summary"]) for r in records if changed]
    return {
        "study_area_id": study_area_id,
        "core": core,
        "buffer": buffer,
        "last": {"version": last["version"], "published_at": last["published_at"]}
        if last
        else None,
        "features": features,
        "coverage": coverage,
        "records": records,
        "changed": changed,
        "changelog": "; ".join(lines),
        "bump": bump,
        "next_version": version,
        "until_record": max((int(r["id"]) for r in records), default=since),
    }


def list_study_areas(db: Session) -> list[dict[str, Any]]:
    """Return every study area with its versions and whether an update is available."""
    out = []
    for row in db.execute(text("SELECT * FROM hub_study_areas ORDER BY id")).mappings():
        area = dict(row)
        changes = pending_changes(db, area["id"])
        packages = [
            dict(p)
            for p in db.execute(
                text(
                    "SELECT id, version, status, bump, created, published_at, archive_sha256, "
                    "bytes, error, job_id, requested_at FROM hub_packages "
                    "WHERE study_area_id = :s ORDER BY id DESC"
                ),
                {"s": area["id"]},
            ).mappings()
        ]
        out.append(
            {
                **area,
                "buffer_municipalities": changes["buffer"],
                "packages": packages,
                "last_version": changes["last"]["version"] if changes["last"] else None,
                "update_available": bool(changes["last"]) and bool(changes["changed"]),
                "pending": changes,
            }
        )
    return out


# --- Publishing --------------------------------------------------------------------------------


def start_publish(
    db: Session,
    settings: Settings,
    runner: JobRunner,
    study_area_id: str,
    comment: str,
    user_id: int | None,
) -> dict[str, Any]:
    """Queue the assembly of the next package version of a study area.

    Raises:
        HubError: If a build is already running, a core municipality has no base data, or
            nothing changed since the last published version.
    """
    area = _study_area(db, study_area_id)
    busy = db.execute(
        text("SELECT version FROM hub_packages WHERE study_area_id = :s AND status = 'building'"),
        {"s": study_area_id},
    ).scalar_one_or_none()
    if busy:
        raise HubError("hub.publish.building", status=409, id=study_area_id, version=busy)
    for mun in area["core_municipalities"]:
        ready = db.execute(
            text("SELECT status FROM hub_onboarding WHERE municipality_id = :m"), {"m": mun}
        ).scalar_one_or_none()
        if ready in (None, "not_started"):
            raise HubError("hub.error.not_onboarded", municipality=mun)
    changes = pending_changes(db, study_area_id)
    if changes["last"] is not None and not changes["changed"]:
        raise HubError(
            "hub.publish.no_changes",
            status=409,
            id=study_area_id,
            version=changes["last"]["version"],
        )
    today = datetime.now(UTC).date()
    record_id = add_record(
        db,
        "package_publish",
        note=PUBLISH_NOTE,
        study_area_id=study_area_id,
        parameters={
            "version": changes["next_version"],
            "bump": changes["bump"],
            "until_record": changes["until_record"],
            "buffer_rule": area["buffer_rule"],
            "buffer_distance_m": area["buffer_distance_m"],
            "comment": comment,
        },
        user_id=user_id,
    )
    package_id = int(
        db.execute(
            text(
                "INSERT INTO hub_packages (study_area_id, version, status, bump, comment, created, "
                "requested_by, record_id) VALUES (:s, :v, 'building', :b, :c, :d, :u, :r) "
                "RETURNING id"
            ),
            {
                "s": study_area_id,
                "v": changes["next_version"],
                "b": changes["bump"],
                "c": comment,
                "d": today,
                "u": user_id,
                "r": record_id,
            },
        ).scalar_one()
    )
    job_id = runner.submit(
        PUBLISH_JOB_KIND, {"package_id": package_id, "record_id": record_id, "user_id": user_id}
    )
    db.execute(
        text("UPDATE hub_packages SET job_id = CAST(:j AS uuid) WHERE id = :id"),
        {"j": job_id, "id": package_id},
    )
    db.execute(
        text("UPDATE hub_processing_records SET job_id = CAST(:j AS uuid) WHERE id = :id"),
        {"j": job_id, "id": record_id},
    )
    return {"package_id": package_id, "version": changes["next_version"], "job_id": job_id}


def run_publish(
    engine: Engine, settings: Settings, ctx: JobContext, payload: Mapping[str, Any]
) -> None:
    """Worker handler of ``hub_publish``: assemble, validate and store the package."""
    package_id = int(payload["package_id"])
    record_id = int(payload["record_id"])
    with Session(engine) as db:
        try:
            _publish(db, settings, ctx, package_id, record_id, payload.get("user_id"))
            db.commit()
        except BaseException as exc:
            db.rollback()
            if isinstance(exc, JobCancelledError):
                entry = check("hub.base.cancelled", "error")
            else:
                entry = check("hub.publish.failed", "error", detail=str(exc) or type(exc).__name__)
            with Session(engine) as fail:
                fail.execute(
                    text("UPDATE hub_packages SET status = 'failed', error = :e WHERE id = :id"),
                    {"e": entry["message"], "id": package_id},
                )
                finish_record(
                    fail,
                    record_id,
                    status="failed",
                    checks=[entry],
                    summary=entry["message"],
                    job_id=ctx.job_id,
                )
                fail.commit()
            raise


def _srs(db: Session, srid: int) -> Srs:
    wkt = db.execute(
        text("SELECT srtext FROM spatial_ref_sys WHERE auth_name = 'EPSG' AND auth_srid = :s"),
        {"s": srid},
    ).scalar_one_or_none()
    return Srs(f"EPSG:{srid}", srid, "EPSG", srid, str(wkt or "undefined"))


def _features(
    db: Session,
    area: Mapping[str, Any],
    core: list[str],
    buffer: list[str],
    publish_date: date,
    previous: Mapping[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    """Select the features of the package (see the module docstring)."""
    municipalities = [*core, *buffer]
    keep = {layer: set(ids) for layer, ids in previous.items()}
    distance = area.get("buffer_distance_m") or 0

    def valid(alias: str = "f") -> str:
        return (
            f"({alias}.valid_to IS NULL OR {alias}.valid_to > :d "
            f"OR {alias}.feature_id = ANY(:prev))"
        )

    def select(
        layer: str, where: str, extra: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            text(
                "SELECT f.feature_id, f.municipality_id, f.properties, f.quality, "
                "f.processing_note, f.valid_from, f.valid_to, ST_AsBinary(f.geom) AS wkb, "
                "ST_XMin(f.geom) AS x0, ST_XMax(f.geom) AS x1, ST_YMin(f.geom) AS y0, "
                "ST_YMax(f.geom) AS y1, GeometryType(f.geom) AS gtype FROM hub_features f "
                f"WHERE f.layer = :l AND {where} ORDER BY f.feature_id"
            ),
            {
                "l": layer,
                "d": publish_date,
                "prev": sorted(keep.get(layer, set())),
                "m": municipalities,
                "core": core,
                "dist": distance,
                **(extra or {}),
            },
        ).mappings()
        return [dict(r) for r in rows]

    out: dict[str, list[dict[str, Any]]] = {}
    out["municipalities"] = select("municipalities", f"f.feature_id = ANY(:m) AND {valid()}")
    if area["buffer_rule"] == "distance":
        unit_where = (
            f"f.municipality_id = ANY(:m) AND {valid()} AND (f.municipality_id = ANY(:core) OR "
            "EXISTS (SELECT 1 FROM hub_features c WHERE c.layer = 'municipalities' "
            "AND c.feature_id = ANY(:core) AND ST_DWithin(f.geom, c.geom, :dist)) "
            "OR f.feature_id = ANY(:prev))"
        )
    else:
        unit_where = f"f.municipality_id = ANY(:m) AND {valid()}"
    out["spatial_units"] = select("spatial_units", unit_where)
    unit_ids = [u["feature_id"] for u in out["spatial_units"]]
    out["facilities"] = select(
        "facilities",
        f"f.municipality_id = ANY(:m) AND {valid()} AND (EXISTS (SELECT 1 FROM hub_features u "
        "WHERE u.layer = 'spatial_units' AND u.feature_id = ANY(:units) "
        "AND u.feature_id = f.properties->>'unit_id') OR f.feature_id = ANY(:prev))",
        {"units": unit_ids},
    )
    wanted_nodes = {u["properties"].get("centroid_node_id") for u in out["spatial_units"]}
    wanted_nodes |= {f["properties"].get("node_id") for f in out["facilities"]}
    out["network_nodes"] = select(
        "network_nodes",
        f"{valid()} AND (EXISTS (SELECT 1 FROM hub_features u WHERE u.layer = 'spatial_units' "
        "AND u.feature_id = ANY(:units) AND ST_Intersects(u.geom, f.geom)) "
        "OR f.feature_id = ANY(:wanted) OR f.feature_id = ANY(:prev))",
        {"units": unit_ids, "wanted": sorted(n for n in wanted_nodes if n)},
    )
    node_ids = [n["feature_id"] for n in out["network_nodes"]]
    out["network_edges"] = select(
        "network_edges",
        f"{valid()} AND f.properties->>'from_node_id' = ANY(:nodes) "
        "AND f.properties->>'to_node_id' = ANY(:nodes)",
        {"nodes": node_ids},
    )
    return out


def _csv(header: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _number(value: object) -> str:
    if value is None:
        return ""
    number = float(str(value))
    return str(int(number)) if number.is_integer() else repr(number)


def _catalogue_rows(
    settings: Settings, source: Mapping[str, Any], columns: Sequence[str]
) -> list[list[str]]:
    with source_path(settings, source).open(encoding="utf-8-sig", newline="") as handle:
        return [[(r.get(c) or "").strip() for c in columns] for r in csv.DictReader(handle)]


def _publish(
    db: Session,
    settings: Settings,
    ctx: JobContext,
    package_id: int,
    record_id: int,
    user_id: int | None,
) -> None:
    pkg = dict(
        db.execute(text("SELECT * FROM hub_packages WHERE id = :id"), {"id": package_id})
        .mappings()
        .one()
    )
    params = db.execute(
        text("SELECT parameters FROM hub_processing_records WHERE id = :id"), {"id": record_id}
    ).scalar_one()
    area = _study_area(db, str(pkg["study_area_id"]))
    core, buffer = study_area_municipalities(db, area)
    last = _last_package(db, area["id"])
    changes = pending_changes(db, area["id"], int(params["until_record"]))
    publish_date: date = pkg["created"]
    previous = {k: list(v) for k, v in (last or {}).get("feature_ids", {}).items()} if last else {}
    ctx.progress(0.1)
    features = _features(db, area, core, buffer, publish_date, previous)
    ctx.progress(0.4)

    latest = latest_sources(db)
    srid = settings.hub_srid
    tables = []
    for layer, columns in LAYER_COLUMNS.items():
        rows = []
        gtypes = set()
        for f in features[layer]:
            props = dict(f["properties"])
            props.update(
                {
                    "municipality_id": f["municipality_id"],
                    "role": "core" if f["municipality_id"] in core else "buffer",
                    "quality": f["quality"],
                    "valid_from": f["valid_from"].isoformat(),
                    "valid_to": f["valid_to"].isoformat() if f["valid_to"] else None,
                    "processing_note": f["processing_note"],
                }
            )
            values = [props.get(c) for c, _ in (*columns, *_META)]
            env = (float(f["x0"]), float(f["x1"]), float(f["y0"]), float(f["y1"]))
            rows.append((blob_from_wkb(bytes(f["wkb"]), srid, env), values))
            gtypes.add(str(f["gtype"]).upper())
        gtype = gtypes.pop() if len(gtypes) == 1 else "GEOMETRY"
        if not rows:
            gtype = {"facilities": "POINT"}.get(layer, "GEOMETRY")
        tables.append((layer, gtype, srid, f"{layer} ({area['id']})", (*columns, *_META), rows))
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "package"
        work.mkdir()
        write_geopackage(
            work / "layers.gpkg",
            [_srs(db, srid)],
            tables,
            f"{publish_date.isoformat()}T00:00:00.000Z",
            reproducible=True,
        )
        ctx.progress(0.6)
        files: dict[str, bytes] = {}
        files["tables/groups.csv"] = _csv(
            ("group_id", "name", "definition_rule"),
            _catalogue_rows(settings, latest["groups"], ("group_id", "name", "definition_rule")),
        )
        services_columns = ("service_id", "name", "service_unit", "max_acceptable_wait")
        files["tables/services.csv"] = _csv(
            services_columns, _catalogue_rows(settings, latest["services"], services_columns)
        )
        files["tables/population.csv"] = _csv(
            ("unit_id", "group_id", "population"),
            [
                (u["feature_id"], g, n)
                for u in features["spatial_units"]
                for g, n in sorted((u["properties"].get("population") or {}).items())
            ],
        )
        files["tables/facility_services.csv"] = _csv(
            ("facility_id", "service_id", "places", "staff", "throughput"),
            [
                (
                    f["feature_id"],
                    sid,
                    _number(s.get("places")),
                    _number(s.get("staff")),
                    _number(s.get("throughput")),
                )
                for f in features["facilities"]
                for sid, s in sorted((f["properties"].get("services") or {}).items())
            ],
        )
        for rel, data in files.items():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            (work / rel).write_bytes(data)
        files["layers.gpkg"] = (work / "layers.gpkg").read_bytes()
        manifest = _manifest(db, settings, area, pkg, core, buffer, changes, last, latest, files)
        (work / "manifest.json").write_bytes(
            (
                json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False, default=str)
                + "\n"
            ).encode()
        )
        ctx.progress(0.8)
        try:
            read_package(work)  # the installation's own validator: a published package imports
        except PackageError as exc:
            raise HubError("hub.publish.invalid", detail=str(exc)) from None
        relative = Path("packages") / area["id"] / str(pkg["version"])
        target = settings.hub_storage_dir / relative
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(work, target)
    archive = archive_directory(target)
    archive_path = target.parent / f"{area['id']}-{pkg['version']}.zip"
    archive_path.write_bytes(archive)
    sha = hashlib.sha256(archive).hexdigest()
    feature_ids = {
        layer: {str(f["feature_id"]): _fingerprint(f, core) for f in fs}
        for layer, fs in features.items()
    }
    db.execute(
        text(
            "UPDATE hub_packages SET status = 'published', manifest = CAST(:m AS jsonb), "
            "feature_ids = CAST(:f AS jsonb), archive_path = :p, archive_sha256 = :s, bytes = :b, "
            "published_at = now() WHERE id = :id"
        ),
        {
            "m": jsonb(manifest),
            "f": jsonb(feature_ids),
            "p": archive_path.relative_to(settings.hub_storage_dir).as_posix(),
            "s": sha,
            "b": len(archive),
            "id": package_id,
        },
    )
    finish_record(
        db,
        record_id,
        status="succeeded",
        outputs={
            "version": pkg["version"],
            "core": core,
            "buffer": buffer,
            "counts": {layer: len(fs) for layer, fs in features.items()},
            "archive_sha256": sha,
        },
        summary=msg("hub.publish.summary", id=area["id"], version=pkg["version"]),
        job_id=ctx.job_id,
    )
    for mun in core:
        set_status(
            db,
            mun,
            "published",
            user_id,
            msg("hub.publish.status_note", id=area["id"], version=pkg["version"]),
            only_from=("base_ready", "facilities_in_progress", "in_review"),
        )
    ctx.progress(0.95)


def _manifest(
    db: Session,
    settings: Settings,
    area: Mapping[str, Any],
    pkg: Mapping[str, Any],
    core: list[str],
    buffer: list[str],
    changes: Mapping[str, Any],
    last: Mapping[str, Any] | None,
    latest: Mapping[str, Mapping[str, Any]],
    files: Mapping[str, bytes],
) -> dict[str, Any]:
    version = str(pkg["version"])
    coverage = municipality_coverage(db, [*core, *buffer])
    changesets = [
        dict(r)
        for r in db.execute(
            text(
                "SELECT DISTINCT licence, attribution FROM hub_changesets "
                "WHERE status = 'approved' AND municipality_id = ANY(:m) ORDER BY 1, 2"
            ),
            {"m": [*core, *buffer]},
        ).mappings()
    ]
    layers: dict[str, dict[str, str]] = {}
    for layer in LAYER_COLUMNS:
        if layer == "facilities":
            licence = "; ".join(sorted({c["licence"] for c in changesets})) or "none"
            attribution = "; ".join(sorted({c["attribution"] for c in changesets})) or "none"
        else:
            source = latest[_SOURCE_OF_LAYER[layer]]
            licence, attribution = str(source["licence"]), str(source["attribution"])
        geometry = "POINT" if layer in ("facilities", "network_nodes") else "GEOMETRY"
        layers[layer] = {
            "table": layer,
            "geometry_type": geometry,
            "licence": licence,
            "attribution": attribution,
        }
    used = [
        latest[t]
        for t in ("boundaries", "spatial_units", "network", "population", "groups", "services")
    ]
    records = [
        dict(r)
        for r in db.execute(
            text(
                "SELECT id, kind, municipality_id, processing_note, inputs, finished_at, summary "
                "FROM hub_processing_records WHERE status = 'succeeded' AND changed "
                "AND id <= :until AND affected_municipalities && :m ORDER BY id"
            ),
            {"until": changes["until_record"], "m": [*core, *buffer]},
        ).mappings()
    ]
    entry_text = str(changes["changelog"]) or msg("hub.publish.initial", id=area["id"])
    comment = str(pkg.get("comment") or "").strip()
    previous = list(last["manifest"].get("changelog", [])) if last else []
    changelog = [
        *previous,
        {
            "version": version,
            "date": pkg["created"].isoformat(),
            "changes": f"{comment} {entry_text}".strip() if comment else entry_text,
        },
    ]
    return {
        "format": "solidaritynode-data-package",
        "schema_version": SCHEMA_VERSION,
        "package_id": area["id"],
        "version": version,
        "created": pkg["created"].isoformat(),
        "synthetic": any(bool(s.get("synthetic")) for s in used),
        "description": f"Data package of study area {area['name']} published by the hub.",
        "crs": settings.hub_crs,
        "study_area": {
            "name": area["name"],
            "core_municipalities": core,
            "buffer_municipalities": buffer,
        },
        "buffer": {
            "rule": area["buffer_rule"],
            "distance_m": area["buffer_distance_m"],
            "description": "Buffer rule configured in the hub; the definition is open (OQ-28).",
        },
        "coverage": {
            mun: {
                layer: {"status": entry["status"], "version": entry["version"]}
                for layer, entry in coverage[mun].items()
            }
            for mun in [*core, *buffer]
        },
        "coverage_layers": list(COVERAGE_LAYERS),
        "layers": layers,
        "sources": [
            {
                "name": s["name"],
                "version": s["version"],
                "licence": s["licence"],
                "attribution": s["attribution"],
                "sha256": s["sha256"],
            }
            for s in used
        ]
        + [
            {
                "name": f"Facility changesets ({c['attribution']})",
                "licence": c["licence"],
                "attribution": c["attribution"],
            }
            for c in changesets
        ],
        "processing_notes": sorted(
            {BASE_NOTE, FACILITY_NOTE, PUBLISH_NOTE, *(str(s["processing_note"]) for s in used)}
        ),
        "provenance": [
            {
                "record": r["id"],
                "kind": r["kind"],
                "municipality_id": r["municipality_id"],
                "processing_note": r["processing_note"],
                "date": r["finished_at"].date().isoformat() if r["finished_at"] else None,
                "summary": r["summary"],
                "inputs": [
                    {
                        k: i.get(k)
                        for k in ("name", "version", "sha256", "file_name", "changeset_id")
                        if i.get(k) is not None
                    }
                    for i in r["inputs"]
                ],
            }
            for r in records
        ],
        "provenance_until_record": changes["until_record"],
        "changelog": changelog,
        "files": [
            {"path": p, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for p, data in sorted(files.items())
        ],
    }


def package_archive(db: Session, settings: Settings, study_area_id: str, version: str) -> Path:
    """Return the ``.zip`` of a published package.

    Raises:
        HubError: If that version is not published.
    """
    path = db.execute(
        text(
            "SELECT archive_path FROM hub_packages WHERE study_area_id = :s AND version = :v "
            "AND status = 'published'"
        ),
        {"s": study_area_id, "v": version},
    ).scalar_one_or_none()
    if path is None:
        raise HubError("hub.error.package_not_found", status=404, id=study_area_id, version=version)
    return settings.hub_storage_dir / str(path)


def source_inputs(db: Session) -> list[dict[str, Any]]:
    """Return how the latest sources are cited (for the publish screen)."""
    return [source_input(s) for s in latest_sources(db).values()]

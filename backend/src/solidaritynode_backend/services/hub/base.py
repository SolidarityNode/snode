"""Base step of onboarding a municipality (Spec 00 §3 Onboarding; DP-003): a background job.

For one municipality plus its buffer (``hub_buffer_rule``; the buffer definition is open,
OQ-28), the job reads the latest registered sources of boundaries, spatial units, network,
population, groups and services **as streams** (a bounding-box prefilter skips rows far from the
area; national files are never loaded whole), selects the features of the area in PostGIS,
assigns **stable ids**, runs the checks and upserts the result into ``hub_features`` in **one
transaction**:

* **ids**: the source's official code where it exists (``municipality_code``, ``unit_code``,
  ``node_code``, ``edge_code``); a unit or edge without a code gets a hub id (``HU-…``,
  ``HE-…``) that is found again by the SHA-256 of its source geometry, so a rerun or a
  neighbour's onboarding reuses it. A feature already present (from an earlier onboarding) is
  reused, never duplicated; one whose source data changed is updated; one that disappeared from
  the source is **closed** (``valid_to``), never deleted.
* **selection**: whole neighbouring municipalities (default) or units within a distance of the
  core municipality. Spatial units are whatever the registered source holds (communities,
  census blocks, grid cells); nothing assumes a kind of unit (the choice for large
  municipalities is open for the Paper 1 spec, ADR 0013). Network nodes inside the selected
  units are kept, and edges whose two ends are kept.
* **checks**: CRS (other CRSs are reprojected and reported), geometry validity, duplicate or
  missing codes, network connectivity (units whose node is outside the largest connected
  part), population (every unit and group, no negative values, totals per municipality equal
  to the source rows). Errors stop the step: nothing is stored and the report says why.
* **unit nodes**: a source column ``centroid_node_code`` is used if present; otherwise the
  network node nearest to a point inside the unit (an assumption recorded in the report and in
  DP-003, not a method choice).

A rerun with the same sources changes nothing (idempotent). The record lists inputs with
versions and checksums, parameters, outputs (ids added, changed, closed per layer) and checks.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.gpkg import GeoPackageError, iter_layer
from solidaritynode_backend.jobs import JobCancelledError, JobContext, JobRunner
from solidaritynode_backend.messages import msg
from solidaritynode_backend.services.hub.common import (
    BASE_NOTE,
    Check,
    HubError,
    add_record,
    check,
    ensure_municipality,
    finish_record,
    jsonb,
    set_status,
)
from solidaritynode_backend.services.hub.sources import (
    PROCESSED_TYPES,
    latest_sources,
    source_input,
    source_path,
)

__all__ = [
    "BASE_JOB_KIND",
    "BaseOutcome",
    "boundary_municipalities",
    "run_base",
    "start_base",
]

log = logging.getLogger("solidaritynode.hub")

BASE_JOB_KIND = "hub_onboard_base"
BATCH = 1000
_CRS = re.compile(r"^EPSG:(\d{4,6})$")


@dataclass
class BaseOutcome:
    """What the base step found and changed."""

    checks: list[Check] = field(default_factory=list)
    layers: dict[str, dict[str, Any]] = field(default_factory=dict)
    area: list[str] = field(default_factory=list)
    affected: set[str] = field(default_factory=set)

    @property
    def errors(self) -> list[Check]:
        """Checks that stop the step."""
        return [c for c in self.checks if c["severity"] == "error"]


# --- Starting the job ----------------------------------------------------------------------


def _table(source: Mapping[str, Any], index: int = 0) -> tuple[str, int]:
    """Return the table name and EPSG code of a registered GeoPackage source."""
    tables = list(source["details"]["tables"].items())
    name, info = tables[index]
    match = _CRS.match(str(info["crs"]))
    if not match:
        raise HubError("hub.base.crs_unknown", source=source["name"], crs=info["crs"])
    return name, int(match.group(1))


def _network_tables(source: Mapping[str, Any]) -> tuple[tuple[str, int], tuple[str, int]]:
    tables = source["details"]["tables"]
    nodes = next(n for n, i in tables.items() if "node_code" in i["columns"])
    edges = next(n for n, i in tables.items() if "edge_code" in i["columns"])
    names = list(tables)
    return _table(source, names.index(nodes)), _table(source, names.index(edges))


def boundary_municipalities(settings: Settings, db: Session) -> list[tuple[str, str]]:
    """Return ``(code, name)`` of every municipality in the latest boundaries source.

    Reads attributes row by row (no geometry is decoded or kept); empty if no boundaries source
    is registered.
    """
    source = latest_sources(db).get("boundaries")
    if source is None:
        return []
    table, _ = _table(source)
    out = []
    for attrs, _ in iter_layer(source_path(settings, source), table):
        out.append((str(attrs.get("municipality_code") or ""), str(attrs.get("name") or "")))
    return sorted(o for o in out if o[0])


def start_base(
    db: Session,
    settings: Settings,
    runner: JobRunner,
    municipality_id: str,
    user_id: int | None,
) -> tuple[int, str]:
    """Queue the base step for a municipality; return ``(record id, job id)``.

    Raises:
        HubError: If a needed source type is not registered, the municipality is not in the
            boundaries source, or a base step for it is already queued or running.
    """
    latest = latest_sources(db)
    if missing := [t for t in PROCESSED_TYPES if t not in latest]:
        raise HubError("hub.base.missing_sources", layers=", ".join(missing))
    names = dict(boundary_municipalities(settings, db))
    if municipality_id not in names:
        raise HubError("hub.error.municipality_unknown", status=404, municipality=municipality_id)
    busy = db.execute(
        text(
            "SELECT 1 FROM hub_onboarding o JOIN jobs j ON j.id = o.last_job_id "
            "WHERE o.municipality_id = :m AND j.status IN ('queued', 'running')"
        ),
        {"m": municipality_id},
    ).first()
    if busy:
        raise HubError("hub.base.already_running", status=409, municipality=municipality_id)
    ensure_municipality(db, municipality_id, names[municipality_id])
    record_id = add_record(
        db,
        "onboarding_base",
        note=BASE_NOTE,
        municipality_id=municipality_id,
        inputs=[source_input(latest[t]) for t in PROCESSED_TYPES],
        parameters={
            "municipality_id": municipality_id,
            "buffer_rule": settings.hub_buffer_rule,
            "buffer_distance_m": settings.hub_buffer_distance_m
            if settings.hub_buffer_rule == "distance"
            else None,
            "crs": settings.hub_crs,
        },
        user_id=user_id,
    )
    job_id = runner.submit(
        BASE_JOB_KIND,
        {"record_id": record_id, "municipality_id": municipality_id, "user_id": user_id},
    )
    db.execute(
        text("UPDATE hub_processing_records SET job_id = CAST(:j AS uuid) WHERE id = :id"),
        {"j": job_id, "id": record_id},
    )
    db.execute(
        text("UPDATE hub_onboarding SET last_job_id = CAST(:j AS uuid) WHERE municipality_id = :m"),
        {"j": job_id, "m": municipality_id},
    )
    return record_id, job_id


# --- The job -------------------------------------------------------------------------------


def run_base(
    engine: Engine, settings: Settings, ctx: JobContext, payload: Mapping[str, Any]
) -> None:
    """Worker handler of ``hub_onboard_base``: one transaction; cancel or failure stores nothing."""
    record_id = int(payload["record_id"])
    with Session(engine) as db:
        try:
            outcome = _base(db, settings, ctx, payload)
        except BaseException as exc:
            db.rollback()
            if isinstance(exc, JobCancelledError):
                entry = check("hub.base.cancelled", "error")
            else:
                entry = check("hub.base.crashed", "error", detail=str(exc) or type(exc).__name__)
            with Session(engine) as fail:
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
        if outcome.errors:
            db.rollback()
            finish_record(
                db,
                record_id,
                status="failed",
                checks=outcome.checks,
                outputs={"area_municipalities": outcome.area},
                summary=msg("hub.base.stopped", errors=len(outcome.errors)),
                job_id=ctx.job_id,
            )
            db.commit()
            return
        counts = {
            k: sum(len(v[k]) for v in outcome.layers.values())
            for k in ("added", "changed", "closed")
        }
        finish_record(
            db,
            record_id,
            status="succeeded",
            checks=outcome.checks,
            outputs={"area_municipalities": outcome.area, "layers": outcome.layers},
            affected=outcome.affected,
            changed=bool(outcome.affected),
            summary=msg(
                "hub.base.summary",
                municipality=payload["municipality_id"],
                added=counts["added"],
                changed=counts["changed"],
                closed=counts["closed"],
            ),
            job_id=ctx.job_id,
        )
        set_status(
            db,
            str(payload["municipality_id"]),
            "base_ready",
            payload.get("user_id"),
            msg("hub.base.status_note", record=record_id),
            only_from=("not_started",),
        )
        db.commit()


@dataclass
class _Sources:
    boundaries: dict[str, Any]
    spatial_units: dict[str, Any]
    network: dict[str, Any]
    population: dict[str, Any]
    groups: dict[str, Any]
    services: dict[str, Any]


def _load_sources(db: Session, record_id: int) -> tuple[_Sources, dict[str, Any]]:
    row = db.execute(
        text("SELECT inputs, parameters FROM hub_processing_records WHERE id = :id"),
        {"id": record_id},
    ).one()
    by_type = {}
    for item in row.inputs:
        source = (
            db.execute(text("SELECT * FROM hub_sources WHERE id = :id"), {"id": item["source_id"]})
            .mappings()
            .one()
        )
        by_type[str(source["layer_type"])] = dict(source)
    return _Sources(**{t: by_type[t] for t in PROCESSED_TYPES}), dict(row.parameters)


def _geom_sql(src_srid: int, hub_srid: int, param: str = "g") -> str:
    base = f"ST_GeomFromWKB(:{param}, {src_srid})"
    return base if src_srid == hub_srid else f"ST_Transform({base}, {hub_srid})"


type BBox = tuple[float, float, float, float]


def _bbox(db: Session, geom_sql: str, srid: int, params: Mapping[str, Any]) -> BBox:
    """Bounding box ``(min_x, min_y, max_x, max_y)`` of a hub-CRS geometry in ``srid``."""
    row = db.execute(
        text(
            f"SELECT ST_XMin(b), ST_YMin(b), ST_XMax(b), ST_YMax(b) FROM "
            f"(SELECT ST_Transform(ST_Envelope({geom_sql}), {srid}) AS b) s"
        ),
        dict(params),
    ).one()
    return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))


def _insert(db: Session, sql: str, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), BATCH):
        db.execute(text(sql), rows[start : start + BATCH])


def _stream_gpkg(
    path: Path, table: str, bbox: BBox | None
) -> Iterator[tuple[dict[str, Any], bytes | None]]:
    try:
        yield from iter_layer(path, table, bbox)
    except GeoPackageError as exc:
        raise HubError("hub.base.source_unreadable", detail=str(exc)) from None


def _base(
    db: Session, settings: Settings, ctx: JobContext, payload: Mapping[str, Any]
) -> BaseOutcome:
    record_id = int(payload["record_id"])
    core = str(payload["municipality_id"])
    sources, params = _load_sources(db, record_id)
    hub = settings.hub_srid
    rule = str(params.get("buffer_rule") or "whole_neighbouring_municipalities")
    distance = float(params.get("buffer_distance_m") or 0.0)
    out = BaseOutcome()
    ctx.progress(0.02)

    for ddl in (
        "CREATE TEMP TABLE hb_mun (code text, name text, geom geometry, valid boolean) "
        "ON COMMIT DROP",
        "CREATE TEMP TABLE hb_unit (code text, key text, name text, mun text, centroid text, "
        "geom geometry) ON COMMIT DROP",
        "CREATE TEMP TABLE hb_node (code text, kind text, geom geometry) ON COMMIT DROP",
        "CREATE TEMP TABLE hb_edge (code text, key text, a text, b text, len double precision, "
        "walk double precision, car double precision, closable boolean, geom geometry) "
        "ON COMMIT DROP",
    ):
        db.execute(text(ddl))

    # 1. Boundaries: find the core municipality, then its neighbours inside its bounding box.
    b_path = source_path(settings, sources.boundaries)
    b_table, b_srid = _table(sources.boundaries)
    if b_srid != hub:
        out.checks.append(
            check(
                "hub.base.reprojected",
                "info",
                source=sources.boundaries["name"],
                source_crs=f"EPSG:{b_srid}",
                crs=f"EPSG:{hub}",
            )
        )
    core_wkb = None
    for attrs, wkb in _stream_gpkg(b_path, b_table, None):
        if str(attrs.get("municipality_code") or "") == core:
            core_wkb = wkb
            break
    if core_wkb is None:
        raise HubError("hub.error.municipality_unknown", municipality=core)
    margin = distance if rule == "distance" else 0.0
    core_geom = _geom_sql(b_srid, hub)
    box = _bbox(db, f"ST_Expand({core_geom}, {margin})", b_srid, {"g": core_wkb})
    rows: list[dict[str, Any]] = []
    for attrs, wkb in _stream_gpkg(b_path, b_table, box):
        code = str(attrs.get("municipality_code") or "").strip()
        if not code or wkb is None:
            out.checks.append(check("hub.base.municipality_without_code", "warning"))
            continue
        rows.append({"c": code, "n": str(attrs.get("name") or code), "g": wkb})
    _insert(
        db,
        f"INSERT INTO hb_mun VALUES (:c, :n, {_geom_sql(b_srid, hub)}, NULL)",
        rows,
    )
    db.execute(text("UPDATE hb_mun SET valid = ST_IsValid(geom)"))
    for (code,) in db.execute(text("SELECT code FROM hb_mun WHERE NOT valid ORDER BY code")):
        out.checks.append(
            check("hub.base.invalid_geometry", "error", layer="municipalities", id=code)
        )
    if rule == "distance":
        selected_sql = (
            "SELECT m.code FROM hb_mun m, hb_mun c WHERE c.code = :core "
            "AND (m.code = :core OR ST_DWithin(m.geom, c.geom, :d))"
        )
    else:
        selected_sql = (
            "SELECT m.code FROM hb_mun m, hb_mun c WHERE c.code = :core "
            "AND (m.code = :core OR ST_Intersects(m.geom, c.geom))"
        )
    selected = sorted(
        {str(r[0]) for r in db.execute(text(selected_sql), {"core": core, "d": distance})}
    )
    out.area = selected
    ctx.progress(0.15)

    # 2. Spatial units of the selected municipalities (or within the distance of the core).
    u_path = source_path(settings, sources.spatial_units)
    u_table, u_srid = _table(sources.spatial_units)
    box = _bbox(
        db,
        "(SELECT ST_Collect(geom) FROM hb_mun WHERE code = ANY(:sel))",
        u_srid,
        {"sel": selected},
    )
    rows = []
    seen_units: set[str] = set()
    for attrs, wkb in _stream_gpkg(u_path, u_table, box):
        if wkb is None:
            continue
        code = str(attrs.get("unit_code") or "").strip()
        key = "geom:" + hashlib.sha256(wkb).hexdigest()
        seen_units.add(code or key)
        rows.append(
            {
                "c": code or None,
                "k": key,
                "n": str(attrs.get("name") or code or ""),
                "m": str(attrs.get("municipality_code") or "").strip(),
                "cn": str(attrs.get("centroid_node_code") or "").strip() or None,
                "g": wkb,
            }
        )
    _insert(
        db,
        f"INSERT INTO hb_unit VALUES (:c, :k, :n, :m, :cn, {_geom_sql(u_srid, hub)})",
        rows,
    )
    if rule == "distance":
        db.execute(
            text(
                "DELETE FROM hb_unit u WHERE NOT (u.mun = :core OR (u.mun = ANY(:sel) AND "
                "ST_DWithin(u.geom, (SELECT geom FROM hb_mun WHERE code = :core), :d)))"
            ),
            {"core": core, "sel": selected, "d": distance},
        )
    else:
        db.execute(text("DELETE FROM hb_unit WHERE NOT (mun = ANY(:sel))"), {"sel": selected})
    for code, n in db.execute(
        text(
            "SELECT code, count(*) FROM hb_unit WHERE code IS NOT NULL "
            "GROUP BY code HAVING count(*) > 1"
        )
    ):
        out.checks.append(
            check("hub.base.duplicate_code", "error", layer="spatial_units", id=code, count=n)
        )
    for (code,) in db.execute(
        text("SELECT coalesce(code, key) FROM hb_unit WHERE NOT ST_IsValid(geom) ORDER BY 1")
    ):
        out.checks.append(
            check("hub.base.invalid_geometry", "error", layer="spatial_units", id=code)
        )
    unit_count = int(
        db.execute(
            text("SELECT count(*) FROM hb_unit WHERE mun = :core"), {"core": core}
        ).scalar_one()
    )
    if unit_count == 0:
        out.checks.append(check("hub.base.no_units", "error", municipality=core))
    if u_srid != hub:
        out.checks.append(
            check(
                "hub.base.reprojected",
                "info",
                source=sources.spatial_units["name"],
                source_crs=f"EPSG:{u_srid}",
                crs=f"EPSG:{hub}",
            )
        )
    ctx.progress(0.3)

    # 3. Population (CSV, streamed): rows of the selected units only.
    unit_codes = {
        str(r[0]): str(r[1])
        for r in db.execute(text("SELECT code, mun FROM hb_unit WHERE code IS NOT NULL"))
    }
    groups = _catalogue(settings, sources.groups, "group_id")
    population, pop_checks = _population(settings, sources.population, unit_codes, groups)
    out.checks.extend(pop_checks)
    ctx.progress(0.45)

    # 4. Network: nodes inside the selected units, edges with both ends kept.
    n_path = source_path(settings, sources.network)
    (n_table, n_srid), (e_table, e_srid) = _network_tables(sources.network)
    box = _bbox(db, "(SELECT ST_Collect(geom) FROM hb_unit)", n_srid, {})
    rows = []
    for attrs, wkb in _stream_gpkg(n_path, n_table, box):
        code = str(attrs.get("node_code") or "").strip()
        if not code or wkb is None:
            out.checks.append(check("hub.base.node_without_code", "error"))
            continue
        rows.append({"c": code, "k": str(attrs.get("kind") or "junction"), "g": wkb})
    _insert(db, f"INSERT INTO hb_node VALUES (:c, :k, {_geom_sql(n_srid, hub)})", rows)
    seen_nodes = {r["c"] for r in rows}
    box = _bbox(db, "(SELECT ST_Collect(geom) FROM hb_unit)", e_srid, {})
    rows = []
    seen_edges: set[str] = set()
    for attrs, wkb in _stream_gpkg(n_path, e_table, box):
        if wkb is None:
            continue
        code = str(attrs.get("edge_code") or "").strip()
        key = "geom:" + hashlib.sha256(wkb).hexdigest()
        seen_edges.add(code or key)
        rows.append(
            {
                "c": code or None,
                "k": key,
                "a": str(attrs.get("from_node") or ""),
                "b": str(attrs.get("to_node") or ""),
                "l": attrs.get("length_m"),
                "w": attrs.get("travel_time_walk_min"),
                "car": attrs.get("travel_time_car_min"),
                "cl": bool(attrs.get("closable") or False),
                "g": wkb,
            }
        )
    _insert(
        db,
        f"INSERT INTO hb_edge VALUES (:c, :k, :a, :b, :l, :w, :car, :cl, {_geom_sql(e_srid, hub)})",
        rows,
    )
    db.execute(
        text(
            "DELETE FROM hb_node n WHERE NOT EXISTS "
            "(SELECT 1 FROM hb_unit u WHERE ST_Intersects(u.geom, n.geom))"
        )
    )
    dropped = db.execute(
        text(
            "DELETE FROM hb_edge e WHERE NOT (e.a IN (SELECT code FROM hb_node) "
            "AND e.b IN (SELECT code FROM hb_node)) RETURNING 1"
        )
    ).all()
    if dropped:
        out.checks.append(check("hub.base.edges_outside", "info", count=len(dropped)))
    for (code,) in db.execute(
        text(
            "SELECT coalesce(code, key) FROM hb_edge WHERE len IS NULL OR walk IS NULL "
            "OR car IS NULL OR len < 0 OR walk < 0 OR car < 0 ORDER BY 1"
        )
    ):
        out.checks.append(check("hub.base.edge_values", "error", id=code))
    if n_srid != hub:
        out.checks.append(
            check(
                "hub.base.reprojected",
                "info",
                source=sources.network["name"],
                source_crs=f"EPSG:{n_srid}",
                crs=f"EPSG:{hub}",
            )
        )
    ctx.progress(0.6)

    # 5. Unit nodes and connectivity.
    nearest = int(
        db.execute(text("SELECT count(*) FROM hb_unit WHERE centroid IS NULL")).scalar_one()
    )
    db.execute(
        text(
            "UPDATE hb_unit u SET centroid = (SELECT n.code FROM hb_node n "
            "ORDER BY n.geom <-> ST_PointOnSurface(u.geom) LIMIT 1) WHERE u.centroid IS NULL"
        )
    )
    if nearest:
        out.checks.append(check("hub.base.centroid_rule", "info", count=nearest))
    for (code,) in db.execute(
        text(
            "SELECT coalesce(code, key) FROM hb_unit WHERE centroid IS NULL "
            "OR centroid NOT IN (SELECT code FROM hb_node) ORDER BY 1"
        )
    ):
        out.checks.append(check("hub.base.unit_without_node", "error", id=code))
    edges = [(str(a), str(b)) for a, b in db.execute(text("SELECT a, b FROM hb_edge"))]
    nodes = [str(r[0]) for r in db.execute(text("SELECT code FROM hb_node"))]
    components = _components(nodes, edges)
    largest = max(components, key=len) if components else set()
    out.checks.append(check("hub.base.components", "info", count=len(components)))
    for code, node in db.execute(
        text("SELECT coalesce(code, key), centroid FROM hb_unit ORDER BY 1")
    ):
        if node and node not in largest:
            out.checks.append(check("hub.base.unit_disconnected", "warning", id=code, node=node))
    ctx.progress(0.7)

    if out.errors:
        return out

    # 6. Upsert into the curated store, assigning stable ids.
    today = datetime.now(UTC).date()
    upsert = _Upsert(db, today, out)
    quality = {
        "municipalities": str(sources.boundaries["quality"]),
        "spatial_units": str(sources.spatial_units["quality"]),
        "network": str(sources.network["quality"]),
        "population": str(sources.population["quality"]),
    }
    for code, name, geom_hex in db.execute(
        text("SELECT code, name, ST_AsEWKB(geom) FROM hb_mun WHERE code = ANY(:sel) ORDER BY code"),
        {"sel": selected},
    ):
        upsert.feature(
            "municipalities",
            code,
            code,
            {"municipality_id": code, "name": name},
            bytes(geom_hex),
            quality["municipalities"],
        )
        ensure_municipality(db, code, name)
    unit_ids: dict[str, str] = {}
    for code, key, name, mun, centroid, geom in db.execute(
        text(
            "SELECT code, key, name, mun, centroid, ST_AsEWKB(geom) FROM hb_unit "
            "ORDER BY coalesce(code, key)"
        )
    ):
        fid = code or upsert.assigned("spatial_units", key, "HU")
        unit_ids[code or key] = fid
        props = {
            "unit_id": fid,
            "name": name,
            "centroid_node_id": centroid,
            "population": population.get(code or "", {}),
            "_source_key": key,
        }
        unit_quality = quality["spatial_units"]
        if quality["population"] == "estimated":
            unit_quality = "estimated"
        upsert.feature("spatial_units", fid, mun, props, bytes(geom), unit_quality)
    ctx.progress(0.8)
    node_mun = {
        str(code): (str(mun), str(unit) if unit else None)
        for code, mun, unit in db.execute(
            text(
                "SELECT n.code, coalesce((SELECT m.code FROM hb_mun m WHERE m.code = ANY(:sel) "
                "AND ST_Covers(m.geom, n.geom) ORDER BY m.code LIMIT 1), "
                "(SELECT u.mun FROM hb_unit u "
                "WHERE ST_Intersects(u.geom, n.geom) ORDER BY u.mun LIMIT 1)), "
                "(SELECT coalesce(u.code, u.key) FROM hb_unit u "
                "WHERE ST_Intersects(u.geom, n.geom) "
                "ORDER BY 1 LIMIT 1) FROM hb_node n"
            ),
            {"sel": selected},
        )
    }
    for code, kind, geom in db.execute(
        text("SELECT code, kind, ST_AsEWKB(geom) FROM hb_node ORDER BY code")
    ):
        mun, unit = node_mun[str(code)]
        props = {"node_id": code, "kind": kind, "unit_id": unit_ids.get(unit or "", unit)}
        upsert.feature("network_nodes", code, mun, props, bytes(geom), quality["network"])
    for code, key, a, b, length, walk, car, closable, geom in db.execute(
        text(
            "SELECT code, key, a, b, len, walk, car, closable, ST_AsEWKB(geom) FROM hb_edge "
            "ORDER BY coalesce(code, key)"
        )
    ):
        fid = code or upsert.assigned("network_edges", key, "HE")
        props = {
            "edge_id": fid,
            "from_node_id": a,
            "to_node_id": b,
            "length_m": float(length),
            "travel_time_walk_min": float(walk),
            "travel_time_car_min": float(car),
            "closable": bool(closable),
            "_source_key": key,
        }
        upsert.feature(
            "network_edges", fid, node_mun[str(a)][0], props, bytes(geom), quality["network"]
        )
    ctx.progress(0.9)

    # 7. Close what disappeared from the source within the selected municipalities.
    seen: dict[str, set[str]] = {
        "municipalities": set(selected)
        | {str(r[0]) for r in db.execute(text("SELECT code FROM hb_mun"))},
        "spatial_units": seen_units,
        "network_nodes": seen_nodes,
        "network_edges": seen_edges,
    }
    for layer, ids in seen.items():
        for fid, mun, props in db.execute(
            text(
                "SELECT feature_id, municipality_id, properties FROM hub_features WHERE layer = :l "
                "AND municipality_id = ANY(:sel) AND valid_to IS NULL"
            ),
            {"l": layer, "sel": selected},
        ):
            if fid not in ids and props.get("_source_key") not in ids:
                db.execute(
                    text(
                        "UPDATE hub_features SET valid_to = :d, updated_at = now() "
                        "WHERE layer = :l AND feature_id = :f"
                    ),
                    {"d": today, "l": layer, "f": fid},
                )
                out.layers[layer]["closed"].append(fid)
                out.affected.add(str(mun))
    # 8. The stored population equals the source rows read for the same units.
    for mun, expected in sorted(population_totals(population, unit_codes).items()):
        stored = int(
            db.execute(
                text(
                    "SELECT coalesce(sum(v::int), 0) FROM hub_features f, "
                    "jsonb_each_text(f.properties->'population') AS p(k, v) "
                    "WHERE f.layer = 'spatial_units' AND f.municipality_id = :m "
                    "AND f.valid_to IS NULL AND f.feature_id = ANY(:units)"
                ),
                {"m": mun, "units": [u for u, m in unit_codes.items() if m == mun]},
            ).scalar_one()
        )
        if stored != expected:
            out.checks.append(
                check(
                    "hub.base.population_mismatch",
                    "error",
                    municipality=mun,
                    stored=stored,
                    source=expected,
                )
            )
    ctx.progress(0.98)
    return out


def population_totals(
    population: Mapping[str, Mapping[str, int]], units: Mapping[str, str]
) -> dict[str, int]:
    """Return the population total per municipality (all groups summed per unit row)."""
    totals: dict[str, int] = defaultdict(int)
    for unit, mun in units.items():
        totals[mun] += sum(population.get(unit, {}).values())
    return dict(totals)


class _Upsert:
    """Insert or update curated features; record added, changed and unchanged ids."""

    def __init__(self, db: Session, today: date, out: BaseOutcome) -> None:
        self.db = db
        self.today = today
        self.out = out
        for layer in ("municipalities", "spatial_units", "network_nodes", "network_edges"):
            out.layers[layer] = {"added": [], "changed": [], "closed": [], "unchanged": 0}

    def assigned(self, layer: str, key: str, prefix: str) -> str:
        """Return the hub id of a feature without a code, found by its geometry hash."""
        existing = self.db.execute(
            text(
                "SELECT feature_id FROM hub_features WHERE layer = :l "
                "AND properties->>'_source_key' = :k"
            ),
            {"l": layer, "k": key},
        ).scalar_one_or_none()
        if existing is not None:
            return str(existing)
        n = int(self.db.execute(text("SELECT nextval('hub_feature_id_seq')")).scalar_one())
        return f"{prefix}-{n:06d}"

    def feature(
        self,
        layer: str,
        fid: str,
        municipality: str,
        props: dict[str, Any],
        geom: bytes,
        quality: str,
    ) -> None:
        """Insert ``fid`` or update it when its data changed."""
        row = self.db.execute(
            text(
                "SELECT properties, municipality_id, quality, valid_to, "
                "ST_AsEWKB(geom) = :g AS same_geom "
                "FROM hub_features WHERE layer = :l AND feature_id = :f FOR UPDATE"
            ),
            {"l": layer, "f": fid, "g": geom},
        ).one_or_none()
        stats = self.out.layers[layer]
        if row is None:
            self.db.execute(
                text(
                    "INSERT INTO hub_features (layer, feature_id, municipality_id, properties, "
                    "geom, quality, processing_note, valid_from) VALUES (:l, :f, :m, "
                    "CAST(:p AS jsonb), ST_GeomFromEWKB(:g), :q, :n, :d)"
                ),
                {
                    "l": layer,
                    "f": fid,
                    "m": municipality,
                    "p": jsonb(props),
                    "g": geom,
                    "q": quality,
                    "n": BASE_NOTE,
                    "d": self.today,
                },
            )
            stats["added"].append(fid)
            self.out.affected.add(municipality)
            return
        same = (
            _public(row.properties) == _public(json.loads(jsonb(props)))
            and row.municipality_id == municipality
            and row.quality == quality
            and row.valid_to is None
            and row.same_geom
        )
        if same:
            stats["unchanged"] += 1
            return
        self.db.execute(
            text(
                "UPDATE hub_features SET properties = CAST(:p AS jsonb), municipality_id = :m, "
                "geom = ST_GeomFromEWKB(:g), quality = :q, valid_to = NULL, updated_at = now() "
                "WHERE layer = :l AND feature_id = :f"
            ),
            {"l": layer, "f": fid, "m": municipality, "p": jsonb(props), "g": geom, "q": quality},
        )
        stats["changed"].append(fid)
        self.out.affected.add(municipality)


def _public(props: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in props.items() if not k.startswith("_")}


def _components(nodes: list[str], edges: list[tuple[str, str]]) -> list[set[str]]:
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups: dict[str, set[str]] = defaultdict(set)
    for n in nodes:
        groups[find(n)].add(n)
    return list(groups.values())


def _csv_rows(
    settings: Settings, source: Mapping[str, Any]
) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(line, row)`` of a registered CSV source, streamed."""
    with source_path(settings, source).open("rb") as raw:
        text_stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_stream)
        for n, row in enumerate(reader, start=2):
            yield n, {k.strip(): (v or "").strip() for k, v in row.items() if k}


def _catalogue(settings: Settings, source: dict[str, Any], key: str) -> set[str]:
    return {row[key] for _, row in _csv_rows(settings, source) if row.get(key)}


_INT = re.compile(r"^\d+$")


def _population(
    settings: Settings,
    source: dict[str, Any],
    units: Mapping[str, str],
    groups: set[str],
) -> tuple[dict[str, dict[str, int]], list[Check]]:
    """Read the population rows of ``units`` (streamed) and check them."""
    checks: list[Check] = []
    values: dict[str, dict[str, int]] = defaultdict(dict)
    for line, row in _csv_rows(settings, source):
        unit = row.get("unit_code", "")
        if unit not in units:
            continue
        group, value = row.get("group_id", ""), row.get("population", "")
        if group not in groups:
            checks.append(
                check("hub.base.population_unknown_group", "error", line=line, group=group)
            )
            continue
        if not _INT.match(value):
            checks.append(check("hub.base.population_not_count", "error", line=line, value=value))
            continue
        if group in values[unit]:
            checks.append(check("hub.base.population_duplicate", "error", unit=unit, group=group))
            continue
        values[unit][group] = int(value)
    for unit, _ in sorted(units.items()):
        missing = sorted(groups - set(values.get(unit, {})))
        if missing:
            checks.append(
                check(
                    "hub.base.population_missing", "warning", unit=unit, groups=", ".join(missing)
                )
            )
    for mun, total in sorted(population_totals(values, units).items()):
        checks.append(check("hub.base.population_total", "info", municipality=mun, total=total))
    return dict(values), checks

#!/usr/bin/env python3
"""Generate the synthetic demo dataset in ``data/synthetic/demo/``.

Everything here is invented: two fictional municipalities placed in open sea (EPSG:2100
coordinates in the Ionian Sea, so they cannot be mistaken for a real place), placeholder
populations, services, facilities and capacities. **No value is a research parameter**; they
only exercise mechanics (loading, joins, shortest paths, scenario overlays).

Standard library only, deterministic (no randomness), so the output is reproducible:

    python3 scripts/generate_demo_data.py

Writes GeoPackage layers (``demo.gpkg``), CSV tables, one scenario as JSON, a ``manifest.json``
with SHA-256 checksums, and the hand-check table of shortest travel times. Processing note:
``docs/data-processing/DP-001-synthetic-demo-dataset.md``.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import sqlite3
import struct
from collections.abc import Iterable, Sequence
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "demo"
GENERATED = "2026-11-24"
PACKAGE_VERSION = "0.1.0"

SRID = 2100
SRS_WKT = (
    'PROJCS["GGRS87 / Greek Grid",GEOGCS["GGRS87",DATUM["Greek_Geodetic_Reference_System_1987",'
    'SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],'
    'TOWGS84[-199.87,74.79,246.62,0,0,0,0],AUTHORITY["EPSG","6121"]],'
    'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4121"]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],'
    'PARAMETER["central_meridian",24],PARAMETER["scale_factor",0.9996],'
    'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],'
    'UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],'
    'AUTHORITY["EPSG","2100"]]'
)
# Origin of the fictional grid, in metres (EPSG:2100). Open sea, about 35° N 20° E.
X0, Y0 = 130_000.0, 3_880_000.0
KM = 1000.0

# Placeholder speeds chosen so that times are round numbers: minutes per kilometre.
MIN_PER_KM = {"walk": 12.0, "car": 2.0}

VALID_FROM = "2026-01-01"

MUNICIPALITIES = [
    # id, name, role, (x0, y0, x1, y1) in km
    ("M-A", "Municipality A (fictional)", "core", (0, 0, 6, 4)),
    ("M-B", "Municipality B (fictional)", "buffer", (6, 0, 8, 4)),
]

UNITS = [
    # unit_id, municipality_id, role, (x0, y0, x1, y1) in km; centroid = square centre
    ("A1", "M-A", "core", (0, 0, 2, 2)),
    ("A2", "M-A", "core", (2, 0, 4, 2)),
    ("A3", "M-A", "core", (4, 0, 6, 2)),
    ("A4", "M-A", "core", (0, 2, 2, 4)),
    ("A5", "M-A", "core", (2, 2, 4, 4)),
    ("A6", "M-A", "core", (4, 2, 6, 4)),
    ("B1", "M-B", "buffer", (6, 0, 8, 2)),
    ("B2", "M-B", "buffer", (6, 2, 8, 4)),
]

GROUPS = [
    ("G-OLD", "Older people (synthetic)", "age >= 65 (placeholder rule)"),
    ("G-MOB", "Mobility-limited (synthetic)", "reported mobility limitation (placeholder rule)"),
    ("G-LOW", "Low income (synthetic)", "household income below a threshold (placeholder rule)"),
]

# Placeholder head counts. Groups may overlap (OQ-6): do not sum across groups.
POPULATION = {
    "A1": (310, 95, 220),
    "A2": (540, 160, 410),
    "A3": (275, 80, 190),
    "A4": (190, 70, 85),
    "A5": (420, 120, 300),
    "A6": (350, 105, 260),
    "B1": (230, 60, 150),
    "B2": (160, 45, 120),
}

SERVICES = [
    # id, name, service unit (core ServiceUnit), placeholder max acceptable wait (ISO 8601)
    ("S-HC", "Home care (synthetic)", "hour", "P7D"),
    ("S-SD", "Social services desk (synthetic)", "appointment", "P14D"),
]

FACILITIES = [
    # id, name, type, municipality, role, node, (x, y) km
    ("F1", "Community centre 1 (fictional)", "community_centre", "M-A", "core", "N-F1", (3, 1.5)),
    ("F2", "Service desk 2 (fictional)", "service_desk", "M-A", "core", "N-F2", (5, 2.5)),
    ("F3", "Care office 3 (fictional)", "care_office", "M-A", "core", "N-F3", (1, 0.5)),
    ("F4", "Community centre 4 (fictional)", "community_centre", "M-B", "buffer", "N-F4", (6.5, 1)),
]

# Placeholder capacity inputs per facility and service: places, staff, throughput.
FACILITY_SERVICES = [
    ("F1", "S-HC", 20, 4, 160),
    ("F1", "S-SD", 10, 2, 120),
    ("F2", "S-SD", 8, 2, 100),
    ("F3", "S-HC", 12, 3, 110),
    ("F4", "S-HC", 15, 3, 130),
    ("F4", "S-SD", 6, 1, 60),
]

# Undirected edges, same for walking and car: id, from, to, length in metres, closable.
EDGES = [
    ("E01", "N-A1", "N-A2", 2000, False),
    ("E02", "N-A2", "N-A3", 2000, True),  # closed in the reference scenario
    ("E03", "N-A3", "N-F4", 1500, False),  # crosses the municipal boundary at x = 6 km
    ("E04", "N-F4", "N-B1", 500, False),
    ("E05", "N-A5", "N-A6", 2000, False),
    ("E06", "N-A6", "N-B2", 2000, False),
    ("E07", "N-A2", "N-F1", 500, False),
    ("E08", "N-F1", "N-A5", 1500, False),
    ("E09", "N-A3", "N-F2", 1500, False),
    ("E10", "N-F2", "N-A6", 500, False),
    ("E11", "N-B1", "N-B2", 2000, False),
    ("E12", "N-A1", "N-F3", 500, False),
    # A4 is badly connected: its only link is a winding road. The length attribute is
    # authoritative; the straight line between the two nodes is shorter.
    ("E13", "N-A4", "N-A5", 5000, False),
]

SCENARIO = {
    "schema": "solidaritynode-scenario/0.1-draft",
    "id": "C-DEMO-REF",
    "version": 1,
    "name": "Demo reference disruption (synthetic)",
    "kind": "disruption",
    "description": (
        "Synthetic disruption for testing mechanics: facility F1 at severity 0.5 and edge "
        "E02 closed for all modes. Not an OQ-16 reference level (minor, moderate, severe)."
    ),
    "facility_severities": {"F1": 0.5},
    "network_disruption": {"modes": ["walk", "car"], "affected_link_ids": ["E02"]},
    "interventions": [],
    "rationing": "uniform",
    "reference_level": None,
}


# --- Geometry encoding (GeoPackage binary = GP header + little-endian WKB) ------------------


def _xy(x_km: float, y_km: float) -> tuple[float, float]:
    return X0 + x_km * KM, Y0 + y_km * KM


def _wkb_point(x: float, y: float) -> bytes:
    return struct.pack("<BIdd", 1, 1, x, y)


def _wkb_polygon(ring: Sequence[tuple[float, float]]) -> bytes:
    out = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring))
    return out + b"".join(struct.pack("<dd", x, y) for x, y in ring)


def _gpkg_blob(wkb: bytes, envelope: tuple[float, float, float, float] | None) -> bytes:
    flags = 0b0000_0001 | ((1 if envelope else 0) << 1)
    head = b"GP" + bytes([0, flags]) + struct.pack("<i", SRID)
    if envelope:
        head += struct.pack("<dddd", *envelope)
    return head + wkb


def _square(box: tuple[float, float, float, float]) -> tuple[bytes, tuple[float, ...]]:
    x0, y0 = _xy(box[0], box[1])
    x1, y1 = _xy(box[2], box[3])
    ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    env = (x0, x1, y0, y1)
    return _gpkg_blob(_wkb_polygon(ring), env), env


def _point(x_km: float, y_km: float) -> tuple[bytes, tuple[float, ...]]:
    x, y = _xy(x_km, y_km)
    return _gpkg_blob(_wkb_point(x, y), None), (x, x, y, y)


# --- GeoPackage writer -----------------------------------------------------------------------


def _init_gpkg(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA application_id = 1196444487")  # 'GPKG'
    db.execute("PRAGMA user_version = 10400")  # GeoPackage 1.4
    db.executescript(
        """
        CREATE TABLE gpkg_spatial_ref_sys (
          srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
          organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
        CREATE TABLE gpkg_contents (
          table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
          identifier TEXT UNIQUE, description TEXT DEFAULT '',
          last_change DATETIME NOT NULL, min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
          srs_id INTEGER, CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
          REFERENCES gpkg_spatial_ref_sys(srs_id));
        CREATE TABLE gpkg_geometry_columns (
          table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL,
          srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
          CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
          CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
          CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id));
        """
    )
    db.executemany(
        "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
            ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
            (
                "WGS 84 geodetic",
                4326,
                "EPSG",
                4326,
                'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
                'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,'
                'AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,'
                'AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]',
                None,
            ),
            ("GGRS87 / Greek Grid", SRID, "EPSG", SRID, SRS_WKT, None),
        ],
    )


def _add_layer(
    db: sqlite3.Connection,
    name: str,
    geometry_type: str,
    description: str,
    columns: Sequence[tuple[str, str]],
    rows: Iterable[tuple[tuple[bytes, tuple[float, ...]], Sequence[object]]],
) -> None:
    cols_sql = ", ".join(f"{c} {t}" for c, t in columns)
    db.execute(
        f"CREATE TABLE {name} (fid INTEGER PRIMARY KEY AUTOINCREMENT, "
        f"geom {geometry_type}, {cols_sql})"
    )
    envs = []
    placeholders = ", ".join("?" for _ in range(len(columns) + 1))
    names = ", ".join(["geom", *(c for c, _ in columns)])
    for (blob, env), values in rows:
        envs.append(env)
        db.execute(f"INSERT INTO {name} ({names}) VALUES ({placeholders})", (blob, *values))
    db.execute(
        "INSERT INTO gpkg_contents VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            name,
            description,
            f"{GENERATED}T00:00:00.000Z",
            min(e[0] for e in envs),
            min(e[2] for e in envs),
            max(e[1] for e in envs),
            max(e[3] for e in envs),
            SRID,
        ),
    )
    db.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
        (name, geometry_type, SRID),
    )


def write_gpkg(path: Path) -> None:
    """Write the spatial layers to a GeoPackage at ``path``."""
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        _init_gpkg(db)
        lifecycle = [("quality", "TEXT"), ("valid_from", "DATE"), ("valid_to", "DATE")]
        _add_layer(
            db,
            "municipalities",
            "POLYGON",
            "Fictional municipalities: M-A study (core), M-B neighbour (buffer)",
            [("municipality_id", "TEXT NOT NULL UNIQUE"), ("name", "TEXT"), ("role", "TEXT")],
            ((_square(box), (mid, name, role)) for mid, name, role, box in MUNICIPALITIES),
        )
        _add_layer(
            db,
            "spatial_units",
            "POLYGON",
            "Fictional spatial units i (6 core in M-A, 2 buffer in M-B)",
            [
                ("unit_id", "TEXT NOT NULL UNIQUE"),
                ("name", "TEXT"),
                ("municipality_id", "TEXT"),
                ("role", "TEXT"),
                *lifecycle,
            ],
            (
                (_square(box), (uid, f"Unit {uid} (fictional)", mid, role, "synthetic", VALID_FROM, None))
                for uid, mid, role, box in UNITS
            ),
        )
        _add_layer(
            db,
            "unit_centroids",
            "POINT",
            "Population centroid of each spatial unit and its network node",
            [("unit_id", "TEXT NOT NULL UNIQUE"), ("node_id", "TEXT")],
            (
                (_point((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), (uid, f"N-{uid}"))
                for uid, _, _, b in UNITS
            ),
        )
        _add_layer(
            db,
            "facilities",
            "POINT",
            "Fictional facilities f (F4 lies in the buffer municipality near the boundary)",
            [
                ("facility_id", "TEXT NOT NULL UNIQUE"),
                ("name", "TEXT"),
                ("facility_type", "TEXT"),
                ("municipality_id", "TEXT"),
                ("role", "TEXT"),
                ("node_id", "TEXT"),
                *lifecycle,
            ],
            (
                (_point(*xy), (fid, name, ftype, mid, role, node, "synthetic", VALID_FROM, None))
                for fid, name, ftype, mid, role, node, xy in FACILITIES
            ),
        )
        db.commit()
        db.execute("VACUUM")
    finally:
        db.close()


# --- Network and hand-check table ----------------------------------------------------------


def nodes() -> list[tuple[str, float, float, str]]:
    """Return ``(node_id, x, y, kind)`` for every network node (x, y in EPSG:2100 metres)."""
    out = []
    for uid, _, _, b in UNITS:
        out.append((f"N-{uid}", *_xy((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), "unit_centroid"))
    for _, _, _, _, _, node, xy in FACILITIES:
        out.append((node, *_xy(*xy), "facility"))
    return out


def shortest_times(mode: str, closed: frozenset[str]) -> dict[str, dict[str, tuple[float, list[str]]]]:
    """Dijkstra from every unit centroid; returns ``{source: {node: (minutes, path)}}``."""
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for eid, a, b, length, _ in EDGES:
        if eid in closed:
            continue
        minutes = length / KM * MIN_PER_KM[mode]
        adjacency.setdefault(a, []).append((b, minutes))
        adjacency.setdefault(b, []).append((a, minutes))
    result = {}
    for uid, *_ in UNITS:
        source = f"N-{uid}"
        best: dict[str, tuple[float, list[str]]] = {}
        heap: list[tuple[float, str, list[str]]] = [(0.0, source, [source])]
        while heap:
            dist, node, path = heapq.heappop(heap)
            if node in best:
                continue
            best[node] = (dist, path)
            for nxt, w in adjacency.get(node, []):
                if nxt not in best:
                    heapq.heappush(heap, (dist + w, nxt, [*path, nxt]))
        result[source] = best
    return result


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _fmt(value: float) -> str:
    return f"{value:g}"


def write_tables(out: Path) -> None:
    """Write all CSV tables and the scenario JSON."""
    _write_csv(out / "groups.csv", ["group_id", "name", "definition_rule"], GROUPS)
    _write_csv(
        out / "population.csv",
        ["unit_id", "group_id", "population"],
        (
            (uid, gid, POPULATION[uid][k])
            for uid, *_ in UNITS
            for k, (gid, _, _) in enumerate(GROUPS)
        ),
    )
    _write_csv(
        out / "services.csv",
        ["service_id", "name", "service_unit", "max_acceptable_wait"],
        SERVICES,
    )
    _write_csv(
        out / "facility_services.csv",
        ["facility_id", "service_id", "places", "staff", "throughput"],
        FACILITY_SERVICES,
    )
    _write_csv(
        out / "network_nodes.csv",
        ["node_id", "x", "y", "kind"],
        ((n, _fmt(x), _fmt(y), kind) for n, x, y, kind in nodes()),
    )
    _write_csv(
        out / "network_edges.csv",
        ["edge_id", "mode", "from_node_id", "to_node_id", "length_m", "travel_time_min", "closable"],
        (
            (eid, mode, a, b, length, _fmt(length / KM * MIN_PER_KM[mode]), str(closable).lower())
            for mode in MIN_PER_KM
            for eid, a, b, length, closable in EDGES
        ),
    )
    closed = frozenset(SCENARIO["network_disruption"]["affected_link_ids"])  # type: ignore[index]
    rows = []
    for scenario_id, closed_edges in (("baseline", frozenset()), (SCENARIO["id"], closed)):
        for mode in MIN_PER_KM:
            table = shortest_times(mode, closed_edges)
            for uid, *_ in UNITS:
                for fid, *_, node, _ in FACILITIES:
                    minutes, path = table[f"N-{uid}"][node]
                    rows.append((scenario_id, mode, uid, fid, _fmt(minutes), " > ".join(path)))
    _write_csv(
        out / "hand_check_travel_times.csv",
        ["scenario_id", "mode", "unit_id", "facility_id", "travel_time_min", "path"],
        rows,
    )
    (out / "scenarios").mkdir(exist_ok=True)
    (out / "scenarios" / f"{SCENARIO['id']}.json").write_text(
        json.dumps(SCENARIO, indent=2) + "\n", encoding="utf-8"
    )


def write_manifest(out: Path) -> None:
    """Write ``manifest.json`` (draft data-package format, ADR 0013) with checksums."""
    files = sorted(
        p for p in out.rglob("*") if p.is_file() and p.name not in {"manifest.json", "README.md"}
    )
    manifest = {
        "format": "solidaritynode-data-package",
        "format_version": "0.1-draft",
        "package_id": "demo-synthetic",
        "version": PACKAGE_VERSION,
        "created": GENERATED,
        "synthetic": True,
        "description": "Synthetic demo dataset for tests and UAT. Placeholder values only; "
        "never read them as research parameters.",
        "crs": f"EPSG:{SRID}",
        "study_area": {
            "core_municipalities": ["M-A"],
            "buffer_municipalities": ["M-B"],
            "buffer_rule": "whole neighbouring municipality (demo only; OQ-28 is open)",
        },
        "coverage": {
            m: {layer: "synthetic" for layer in ("boundaries", "population", "facilities", "network")}
            for m in ("M-A", "M-B")
        },
        "processing_notes": ["DP-001"],
        "provenance": "Generated by scripts/generate_demo_data.py (standard library, no randomness).",
        "licence": "AGPL-3.0-or-later (synthetic data, part of the repository)",
        "changelog": [{"version": PACKAGE_VERSION, "date": GENERATED, "changes": "Initial demo dataset."}],
        "files": [
            {
                "path": p.relative_to(out).as_posix(),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            for p in files
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Regenerate the demo dataset."""
    OUT.mkdir(parents=True, exist_ok=True)
    write_gpkg(OUT / "demo.gpkg")
    write_tables(OUT)
    write_manifest(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the two synthetic demo data packages from the demo dataset (DP-002).

Writes ``data/synthetic/packages/demo-1.0.0/`` and ``demo-1.1.0/`` in the v0.1 data package
format (ADR 0013): a ``manifest.json`` plus GeoJSON layers and CSV tables, every file listed
with its SHA-256 checksum.

* **1.0.0**: municipality A (``M-A``, core) is onboarded, its facilities are verified.
  Neighbour B (``M-B``) is present only as buffer: boundaries, population and network, but
  ``facilities: missing``.
* **1.1.0**: B is onboarded: its cross-border facility ``F4`` is added as verified; facility
  ``F2`` gets a corrected capacity; facility ``F3`` is closed (``valid_to`` set, never deleted).

Everything is synthetic (see ``data/synthetic/demo/README.md``); quality labels and coverage
statuses are invented to exercise the platform. Geometries and attributes come from the
constants of ``generate_demo_data.py``; the hand-check travel times are **copied** from the
demo dataset (an independent computation) and only filtered to the facilities present in each
version, so they can check the platform's own shortest paths.

Standard library only, deterministic, byte-for-byte reproducible::

    python3 scripts/build_demo_packages.py [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_demo_data as demo  # noqa: E402  (sibling script, constants only)

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "data" / "synthetic" / "demo"
OUT = ROOT / "data" / "synthetic" / "packages"

PACKAGE_ID = "demo-study-area-a"
SCHEMA_VERSION = "1.0"
NOTE = "DP-002"
LAYERS = ("boundaries", "population", "network", "facilities", "transit")
CRS_URN = "urn:ogc:def:crs:EPSG::2100"


@dataclass(frozen=True)
class Version:
    """What differs between the two demo package versions."""

    version: str
    created: str
    facilities: tuple[str, ...]
    closed: Mapping[str, str] = field(default_factory=dict)  # facility id -> valid_to
    capacity: Mapping[tuple[str, str], tuple[float, float, float]] = field(default_factory=dict)
    coverage: Mapping[str, Mapping[str, tuple[str, str]]] = field(default_factory=dict)
    changelog: tuple[tuple[str, str, str], ...] = ()


_COVERAGE_A = {
    "boundaries": ("open_data", "1.0.0"),
    "population": ("open_data", "1.0.0"),
    "network": ("open_data", "1.0.0"),
    "facilities": ("verified", "1.0.0"),
    "transit": ("missing", "1.0.0"),
}
_COVERAGE_B_100 = {
    "boundaries": ("open_data", "1.0.0"),
    "population": ("estimated", "1.0.0"),
    "network": ("open_data", "1.0.0"),
    "facilities": ("missing", "1.0.0"),
    "transit": ("missing", "1.0.0"),
}
_LOG_100 = (
    "1.0.0",
    "2026-11-24",
    "Initial package: municipality M-A onboarded (facilities verified). Neighbour M-B in the "
    "buffer with boundaries, estimated population and network only; its facilities are missing.",
)
_LOG_110 = (
    "1.1.0",
    "2026-12-01",
    "M-B onboarded: cross-border facility F4 added (verified). F2: corrected capacity for "
    "S-SD (throughput 100 -> 90). F3 closed on 2026-12-01 (valid_to set; kept for history).",
)

VERSIONS = (
    Version(
        version="1.0.0",
        created="2026-11-24",
        facilities=("F1", "F2", "F3"),
        coverage={"M-A": _COVERAGE_A, "M-B": _COVERAGE_B_100},
        changelog=(_LOG_100,),
    ),
    Version(
        version="1.1.0",
        created="2026-12-01",
        facilities=("F1", "F2", "F3", "F4"),
        closed={"F3": "2026-12-01"},
        capacity={("F2", "S-SD"): (8, 2, 90)},
        coverage={
            "M-A": {**_COVERAGE_A, "facilities": ("verified", "1.1.0")},
            "M-B": {**_COVERAGE_B_100, "facilities": ("verified", "1.1.0")},
        },
        changelog=(_LOG_100, _LOG_110),
    ),
)

# Invented per-feature quality labels (synthetic): A's units from open data, B's estimated.
_UNIT_QUALITY = {"M-A": "open_data", "M-B": "estimated"}


def _xy(x_km: float, y_km: float) -> list[float]:
    x, y = demo._xy(x_km, y_km)
    return [x, y]


def _ring(box: Sequence[float]) -> list[list[float]]:
    x0, y0, x1, y1 = box
    return [_xy(x0, y0), _xy(x1, y0), _xy(x1, y1), _xy(x0, y1), _xy(x0, y0)]


def _unit_of_point(x_km: float, y_km: float) -> str:
    for uid, _, _, (x0, y0, x1, y1) in demo.UNITS:
        if x0 <= x_km < x1 and y0 <= y_km < y1:
            return uid
    raise ValueError(f"point ({x_km}, {y_km}) outside every unit")


def _meta(municipality: str, role: str, quality: str, valid_to: str | None = None) -> dict[str, Any]:
    return {
        "municipality_id": municipality,
        "role": role,
        "quality": quality,
        "valid_from": demo.VALID_FROM,
        "valid_to": valid_to,
        "processing_note": NOTE,
    }


def _collection(name: str, features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": name,
        "crs": {"type": "name", "properties": {"name": CRS_URN}},
        "features": features,
    }


def _feature(fid: str, props: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "id": fid, "properties": props, "geometry": geometry}


def _node_table() -> dict[str, tuple[float, float, str, str]]:
    """Return ``node -> (x_km, y_km, kind, unit_id)``."""
    out: dict[str, tuple[float, float, str, str]] = {}
    for uid, _, _, (x0, y0, x1, y1) in demo.UNITS:
        out[f"N-{uid}"] = ((x0 + x1) / 2, (y0 + y1) / 2, "unit_centroid", uid)
    for _, _, _, _, _, node, (x, y) in demo.FACILITIES:
        out[node] = (x, y, "facility_access", _unit_of_point(x, y))
    return out


def _municipality_of_unit(uid: str) -> tuple[str, str]:
    for u, mun, role, _ in demo.UNITS:
        if u == uid:
            return mun, role
    raise KeyError(uid)


def build_layers(v: Version) -> dict[str, Any]:
    """Return ``{relative path: content}`` (dict for GeoJSON, rows for CSV)."""
    municipalities = [
        _feature(
            mid,
            {"municipality_id": mid, "name": name, **_meta(mid, role, "open_data")},
            {"type": "Polygon", "coordinates": [_ring(box)]},
        )
        for mid, name, role, box in demo.MUNICIPALITIES
    ]
    units = [
        _feature(
            uid,
            {
                "unit_id": uid,
                "name": f"Unit {uid} (fictional)",
                "centroid_node_id": f"N-{uid}",
                **_meta(mun, role, _UNIT_QUALITY[mun]),
            },
            {"type": "Polygon", "coordinates": [_ring(box)]},
        )
        for uid, mun, role, box in demo.UNITS
    ]
    facilities = []
    for fid, name, ftype, mun, role, node, (x, y) in demo.FACILITIES:
        if fid not in v.facilities:
            continue
        props = {
            "facility_id": fid,
            "name": name,
            "facility_type": ftype,
            "node_id": node,
            "unit_id": _unit_of_point(x, y),
            **_meta(mun, role, "verified_by_municipality", v.closed.get(fid)),
        }
        facilities.append(_feature(fid, props, {"type": "Point", "coordinates": _xy(x, y)}))
    table = _node_table()
    nodes = []
    for nid, (x, y, kind, uid) in table.items():
        mun, role = _municipality_of_unit(uid)
        props = {"node_id": nid, "kind": kind, "unit_id": uid, **_meta(mun, role, "open_data")}
        nodes.append(_feature(nid, props, {"type": "Point", "coordinates": _xy(x, y)}))
    edges = []
    for eid, a, b, length, closable in demo.EDGES:
        mun, role = _municipality_of_unit(table[a][3])
        props = {
            "edge_id": eid,
            "from_node_id": a,
            "to_node_id": b,
            "length_m": length,
            "travel_time_walk_min": length / demo.KM * demo.MIN_PER_KM["walk"],
            "travel_time_car_min": length / demo.KM * demo.MIN_PER_KM["car"],
            "closable": closable,
            **_meta(mun, role, "open_data"),
        }
        line = [_xy(table[a][0], table[a][1]), _xy(table[b][0], table[b][1])]
        edges.append(_feature(eid, props, {"type": "LineString", "coordinates": line}))

    population = [
        (uid, gid, demo.POPULATION[uid][k])
        for uid, *_ in demo.UNITS
        for k, (gid, *_) in enumerate(demo.GROUPS)
    ]
    services = [(sid, name, unit, wait) for sid, name, unit, wait in demo.SERVICES]
    capacity = []
    for fid, sid, places, staff, throughput in demo.FACILITY_SERVICES:
        if fid in v.facilities:
            capacity.append((fid, sid, *v.capacity.get((fid, sid), (places, staff, throughput))))
    open_facilities = set(v.facilities) - set(v.closed)
    checks = []
    with (DEMO_DIR / "hand_check_travel_times.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["facility_id"] not in open_facilities:
                continue
            closed = "" if row["scenario_id"] == "baseline" else "E02"
            checks.append(
                (closed, row["mode"], row["unit_id"], row["facility_id"], row["travel_time_min"])
            )
    return {
        "layers/municipalities.geojson": _collection("municipalities", municipalities),
        "layers/spatial_units.geojson": _collection("spatial_units", units),
        "layers/facilities.geojson": _collection("facilities", facilities),
        "layers/network_nodes.geojson": _collection("network_nodes", nodes),
        "layers/network_edges.geojson": _collection("network_edges", edges),
        "tables/groups.csv": (["group_id", "name", "definition_rule"], demo.GROUPS),
        "tables/population.csv": (["unit_id", "group_id", "population"], population),
        "tables/services.csv": (
            ["service_id", "name", "service_unit", "max_acceptable_wait"],
            services,
        ),
        "tables/facility_services.csv": (
            ["facility_id", "service_id", "places", "staff", "throughput"],
            capacity,
        ),
        "checks/hand_check_travel_times.csv": (
            ["closed_edges", "mode", "unit_id", "facility_id", "travel_time_min"],
            checks,
        ),
    }


def _csv_bytes(header: Sequence[str], rows: Iterable[Sequence[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _json_bytes(content: Any) -> bytes:
    return (json.dumps(content, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def manifest(v: Version, files: Mapping[str, bytes]) -> dict[str, Any]:
    """Return the package manifest (ADR 0013, v0.1 format)."""
    return {
        "format": "solidaritynode-data-package",
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "version": v.version,
        "created": v.created,
        "synthetic": True,
        "description": (
            "Synthetic demo package for tests and UAT. Placeholder values and invented "
            "quality labels only; never read them as research parameters."
        ),
        "crs": "EPSG:2100",
        "study_area": {
            "name": "Demo study area A (fictional)",
            "core_municipalities": ["M-A"],
            "buffer_municipalities": ["M-B"],
        },
        "buffer": {
            "rule": "whole_neighbouring_municipalities",
            "description": "Whole neighbouring municipality (demo choice only; OQ-28 is open).",
        },
        "coverage": {
            mun: {layer: {"status": s, "version": ver} for layer, (s, ver) in layers.items()}
            for mun, layers in v.coverage.items()
        },
        "sources": [
            {
                "name": "SolidarityNode synthetic demo dataset",
                "licence": "AGPL-3.0-or-later",
                "attribution": "Synthetic data generated by scripts/generate_demo_data.py",
            }
        ],
        "processing_notes": ["DP-001", NOTE],
        "changelog": [{"version": a, "date": b, "changes": c} for a, b, c in v.changelog],
        "files": [
            {"path": p, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for p, data in sorted(files.items())
        ],
    }


def build(out: Path) -> list[Path]:
    """Write every demo package version under ``out`` and return the package directories."""
    written = []
    for v in VERSIONS:
        files: dict[str, bytes] = {}
        for path, content in build_layers(v).items():
            if path.endswith(".csv"):
                files[path] = _csv_bytes(*content)
            else:
                files[path] = _json_bytes(content)
        target = out / f"demo-{v.version}"
        for path, data in files.items():
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            (target / path).write_bytes(data)
        (target / "manifest.json").write_bytes(_json_bytes(manifest(v, files)))
        written.append(target)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Build the synthetic demo data packages.")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    for path in build(args.out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate the synthetic "national" raw sources and demo facility files for the hub (DP-005).

Writes ``data/synthetic/demo/hub/``:

* ``sources/``: raw sources as a national provider would deliver them, covering **four**
  fictional municipalities, so onboarding only some of them can be tested:

  - ``boundaries.gpkg`` (table ``municipalities``: ``municipality_code``, ``name``);
  - ``spatial_units.gpkg`` (table ``spatial_units``: ``unit_code``, ``name``,
    ``municipality_code``). The unit is data, not an assumption: here square "communities";
  - ``network.gpkg`` (tables ``nodes``: ``node_code``; ``edges``: ``edge_code``, ``from_node``,
    ``to_node``, ``length_m``, ``travel_time_walk_min``, ``travel_time_car_min``, ``closable``);
  - ``population.csv`` (``unit_code``, ``group_id``, ``population``);
  - ``groups.csv`` and ``services.csv`` (the catalogue of groups and services);
  - ``sources.json``: the metadata used to register each file (``make uat-hub``).

* ``imports/``: facility files for the import screen: a valid file for each of M-A and M-B, a
  file with deliberate errors, a file with personal-data columns, and an update of M-A.

Municipalities A and B and their units, groups, services, population, facilities and network
are those of the demo dataset (``generate_demo_data.py``), so hub packages use the same ids.
C lies north of A (it touches A4 and A5 only) and D east of B. Everything is invented and lies
in open sea; **no value is a research parameter**.

Standard library only, deterministic::

    python3 scripts/generate_hub_sources.py [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_demo_data as demo  # noqa: E402  (sibling script, constants only)
from solidaritynode_backend.gpkg import write_geopackage  # noqa: E402  (standard library only)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "synthetic" / "demo" / "hub"
GENERATED = "2026-11-26"
SOURCE_VERSION = "2026-11"
NOTE = "DP-005"

MUNICIPALITIES = [
    # code, name, (x0, y0, x1, y1) in km
    ("M-A", "Municipality A (fictional)", (0, 0, 6, 4)),
    ("M-B", "Municipality B (fictional)", (6, 0, 8, 4)),
    ("M-C", "Municipality C (fictional)", (0, 4, 3, 6)),
    ("M-D", "Municipality D (fictional)", (8, 0, 10, 4)),
]
UNITS = [
    *((uid, mun, box) for uid, mun, _, box in demo.UNITS),
    ("C1", "M-C", (0, 4, 1.5, 6)),
    ("C2", "M-C", (1.5, 4, 3, 6)),
    ("D1", "M-D", (8, 0, 10, 2)),
    ("D2", "M-D", (8, 2, 10, 4)),
]
POPULATION = {
    **demo.POPULATION,
    "C1": (150, 40, 90),
    "C2": (120, 30, 70),
    "D1": (200, 55, 140),
    "D2": (180, 50, 110),
}
EDGES = [
    *demo.EDGES,
    ("E14", "N-A4", "N-C1", 2000, False),  # crosses the boundary A/C
    ("E15", "N-C1", "N-C2", 1500, False),
    ("E16", "N-B1", "N-D1", 2000, False),  # crosses the boundary B/D
    ("E17", "N-D1", "N-D2", 2000, False),
    ("E18", "N-B2", "N-D2", 2000, False),
]
FACILITY_NODES = {node: (x, y) for _, _, _, _, _, node, (x, y) in demo.FACILITIES}

# Facility files (import template columns, docs/data-processing/facility-import.md).
FACILITY_COLUMNS = [
    "facility_id",
    "external_id",
    "name",
    "municipality",
    "x",
    "y",
    "lon",
    "lat",
    "address",
    "facility_type",
    "service_id",
    "places",
    "staff",
    "throughput",
    "throughput_unit",
    "operating_hours",
    "status",
    "quality",
    "public_phone",
    "public_email",
    "source",
    "notes",
]
SERVICE_UNIT = {sid: unit for sid, _, unit, _ in demo.SERVICES}
HOURS = "Mon-Fri 08:00-16:00"


def _xy(x_km: float, y_km: float) -> tuple[float, float]:
    return demo._xy(x_km, y_km)


def _ring(box: Sequence[float]) -> list[list[float]]:
    x0, y0, x1, y1 = box
    return [list(_xy(*p)) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]


def _nodes() -> dict[str, tuple[float, float]]:
    out = {f"N-{uid}": ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for uid, _, b in UNITS}
    out.update(FACILITY_NODES)
    return out


def write_sources(out: Path) -> None:
    """Write the raw source files and ``sources.json``."""
    out.mkdir(parents=True, exist_ok=True)
    srs = [demo.GREEK_GRID]
    stamp = f"{GENERATED}T00:00:00.000Z"
    mun_rows = [
        ({"type": "Polygon", "coordinates": [_ring(box)]}, [code, name])
        for code, name, box in MUNICIPALITIES
    ]
    write_geopackage(
        out / "boundaries.gpkg",
        srs,
        [
            (
                "municipalities",
                "POLYGON",
                demo.SRID,
                "Synthetic municipal boundaries (national source)",
                (("municipality_code", "TEXT"), ("name", "TEXT")),
                mun_rows,
            )
        ],
        stamp,
        reproducible=True,
    )
    unit_rows = [
        (
            {"type": "Polygon", "coordinates": [_ring(box)]},
            [uid, f"Unit {uid} (fictional)", mun],
        )
        for uid, mun, box in UNITS
    ]
    write_geopackage(
        out / "spatial_units.gpkg",
        srs,
        [
            (
                "spatial_units",
                "POLYGON",
                demo.SRID,
                "Synthetic spatial units (national source)",
                (("unit_code", "TEXT"), ("name", "TEXT"), ("municipality_code", "TEXT")),
                unit_rows,
            )
        ],
        stamp,
        reproducible=True,
    )
    nodes = _nodes()
    node_rows = [
        ({"type": "Point", "coordinates": list(_xy(x, y))}, [nid])
        for nid, (x, y) in sorted(nodes.items())
    ]
    edge_rows = []
    for eid, a, b, length, closable in EDGES:
        line = [list(_xy(*nodes[a])), list(_xy(*nodes[b]))]
        edge_rows.append(
            (
                {"type": "LineString", "coordinates": line},
                [
                    eid,
                    a,
                    b,
                    float(length),
                    length / demo.KM * demo.MIN_PER_KM["walk"],
                    length / demo.KM * demo.MIN_PER_KM["car"],
                    1 if closable else 0,
                ],
            )
        )
    write_geopackage(
        out / "network.gpkg",
        srs,
        [
            (
                "nodes",
                "POINT",
                demo.SRID,
                "Synthetic network nodes",
                (("node_code", "TEXT"),),
                node_rows,
            ),
            (
                "edges",
                "LINESTRING",
                demo.SRID,
                "Synthetic network edges",
                (
                    ("edge_code", "TEXT"),
                    ("from_node", "TEXT"),
                    ("to_node", "TEXT"),
                    ("length_m", "REAL"),
                    ("travel_time_walk_min", "REAL"),
                    ("travel_time_car_min", "REAL"),
                    ("closable", "BOOLEAN"),
                ),
                edge_rows,
            ),
        ],
        stamp,
        reproducible=True,
    )
    _write_csv(
        out / "population.csv",
        ["unit_code", "group_id", "population"],
        [
            (uid, gid, POPULATION[uid][k])
            for uid, _, _ in UNITS
            for k, (gid, *_) in enumerate(demo.GROUPS)
        ],
    )
    _write_csv(out / "groups.csv", ["group_id", "name", "definition_rule"], demo.GROUPS)
    _write_csv(
        out / "services.csv",
        ["service_id", "name", "service_unit", "max_acceptable_wait"],
        demo.SERVICES,
    )
    common = {
        "coverage": "national",
        "version": SOURCE_VERSION,
        "licence": "AGPL-3.0-or-later",
        "attribution": "Synthetic data generated by scripts/generate_hub_sources.py",
        "processing_note": NOTE,
        "quality": "open_data",
    }
    metadata = [
        {"file": "boundaries.gpkg", "name": "Synthetic national boundaries",
         "layer_type": "boundaries", **common},
        {"file": "spatial_units.gpkg", "name": "Synthetic national spatial units",
         "layer_type": "spatial_units", **common},
        {"file": "network.gpkg", "name": "Synthetic national road network",
         "layer_type": "network", **common},
        {"file": "population.csv", "name": "Synthetic national population",
         "layer_type": "population", **common},
        {"file": "groups.csv", "name": "Synthetic social groups", "layer_type": "groups",
         **common},
        {"file": "services.csv", "name": "Synthetic services", "layer_type": "services",
         **common},
    ]
    (out / "sources.json").write_text(json.dumps(metadata, indent=1) + "\n", encoding="utf-8")


def _facility_rows(
    facilities: Iterable[tuple[str, str, str, str, tuple[float, float]]],
    *,
    quality: str = "verified_by_municipality",
    capacity: dict[tuple[str, str], tuple[float, float, float]] | None = None,
) -> list[dict[str, Any]]:
    """Rows of the import template: one row per facility and service."""
    rows = []
    for ext, name, ftype, mun, (x_km, y_km) in facilities:
        x, y = _xy(x_km, y_km)
        services = [s for s in demo.FACILITY_SERVICES if s[0] == _demo_id(name)]
        for _, sid, places, staff, throughput in services or [("", "S-SD", 4, 1, 40)]:
            places, staff, throughput = (capacity or {}).get(
                (ext, sid), (places, staff, throughput)
            )
            rows.append(
                {
                    "facility_id": "",
                    "external_id": ext,
                    "name": name,
                    "municipality": mun,
                    "x": f"{x:.1f}",
                    "y": f"{y:.1f}",
                    "lon": "",
                    "lat": "",
                    "address": "",
                    "facility_type": ftype,
                    "service_id": sid,
                    "places": places,
                    "staff": staff,
                    "throughput": throughput,
                    "throughput_unit": SERVICE_UNIT[sid],
                    "operating_hours": HOURS,
                    "status": "open",
                    "quality": quality,
                    "public_phone": "2100000000",
                    "public_email": "info@example.org",
                    "source": "Synthetic municipal register (fictional)",
                    "notes": "",
                }
            )
    return rows


def _demo_id(name: str) -> str:
    for fid, fname, *_ in demo.FACILITIES:
        if fname == name:
            return fid
    return ""


def _demo_facilities(municipality: str) -> list[tuple[str, str, str, str, tuple[float, float]]]:
    return [
        (f"REG-{fid}", name, ftype, mun, xy)
        for fid, name, ftype, mun, _, _, xy in demo.FACILITIES
        if mun == municipality
    ]


def write_imports(out: Path) -> None:
    """Write the demo facility import files."""
    out.mkdir(parents=True, exist_ok=True)
    _write_dicts(out / "facilities-M-A.csv", _facility_rows(_demo_facilities("M-A")))
    _write_dicts(out / "facilities-M-B.csv", _facility_rows(_demo_facilities("M-B")))

    errors = _facility_rows(_demo_facilities("M-A"))
    errors[0]["name"] = ""  # required field missing
    errors[1]["service_id"] = "S-XX"  # unknown service type
    errors[2]["throughput_unit"] = "visit"  # wrong unit for S-SD (appointment)
    errors[3]["x"], errors[3]["y"] = f"{_xy(7, 1)[0]:.1f}", f"{_xy(7, 1)[1]:.1f}"  # in M-B
    _write_dicts(out / "facilities-M-A-errors.csv", errors)

    personal = _facility_rows(_demo_facilities("M-A"))
    for row in personal:
        row["contact_person"] = "Maria Example (fictional)"
        row["mobile"] = "6900000000"
    personal[0]["public_phone"] = "6912345678"  # a mobile number in the public phone column
    _write_dicts(
        out / "facilities-M-A-personal.csv", personal, [*FACILITY_COLUMNS, "contact_person", "mobile"]
    )

    # Update of M-A after the first import: one correction (by hub id) and one new facility.
    update = _facility_rows(
        [("REG-F2", "Service desk 2 (fictional)", "service_desk", "M-A", (5, 2.5))],
        capacity={("REG-F2", "S-SD"): (8, 2, 90)},
    )
    update[0]["facility_id"] = "HF-000002"
    update[0]["notes"] = "Throughput corrected by the municipality (100 -> 90)."
    update += _facility_rows(
        [("REG-F5", "Day centre 5 (fictional)", "day_centre", "M-A", (2.5, 3.0))],
        quality="estimated",
    )
    _write_dicts(out / "facilities-M-A-update.csv", update)


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _write_dicts(
    path: Path, rows: list[dict[str, Any]], columns: Sequence[str] = FACILITY_COLUMNS
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Generate the synthetic hub sources.")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    write_sources(args.out / "sources")
    write_imports(args.out / "imports")
    print(f"wrote {args.out}/sources and {args.out}/imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

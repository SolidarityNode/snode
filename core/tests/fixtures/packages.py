"""Read a synthetic demo data package (``data/synthetic/packages/``) into a StudyArea, for tests.

Standard library only (``sqlite3`` reads the attribute columns of ``layers.gpkg``; geometries are
not needed); mirrors what the backend loads from the database. Closed facilities
(``valid_to`` on or before the package date) are left out, as the backend does.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from solidaritynode_core.model import (
    CapacityInputs,
    Facility,
    FacilityId,
    GroupId,
    HandCheck,
    NetworkEdge,
    PopulationGroup,
    Service,
    ServiceId,
    ServiceUnit,
    SpatialUnit,
    StudyArea,
    TransportMode,
    UnitId,
)

PACKAGES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "packages"


def _features(pkg: Path, layer: str) -> list[dict[str, Any]]:
    with sqlite3.connect(f"file:{pkg / 'layers.gpkg'}?mode=ro", uri=True) as db:
        cursor = db.execute(f"SELECT * FROM {layer} ORDER BY fid")
        names = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    return [
        {k: v for k, v in zip(names, row, strict=True) if k not in ("fid", "geom")} for row in rows
    ]


def _rows(pkg: Path, name: str) -> list[dict[str, str]]:
    with (pkg / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load(version: str) -> StudyArea:
    pkg = PACKAGES / f"demo-{version}"
    manifest = json.loads((pkg / "manifest.json").read_text("utf-8"))
    created = manifest["created"]
    population: dict[str, dict[GroupId, float]] = {}
    for row in _rows(pkg, "tables/population.csv"):
        population.setdefault(row["unit_id"], {})[GroupId(row["group_id"])] = float(
            row["population"]
        )
    units = _features(pkg, "spatial_units")
    capacity: dict[str, dict[ServiceId, CapacityInputs]] = {}
    for row in _rows(pkg, "tables/facility_services.csv"):
        capacity.setdefault(row["facility_id"], {})[ServiceId(row["service_id"])] = CapacityInputs(
            float(row["places"]), float(row["staff"]), float(row["throughput"])
        )
    facilities = [
        f for f in _features(pkg, "facilities") if f["valid_to"] is None or f["valid_to"] > created
    ]
    nodes = _features(pkg, "network_nodes")
    return StudyArea(
        package_id=manifest["package_id"],
        package_version=manifest["version"],
        units=tuple(
            SpatialUnit(UnitId(u["unit_id"]), population_by_group=population[u["unit_id"]])
            for u in units
        ),
        unit_roles={UnitId(u["unit_id"]): u["role"] for u in units},
        unit_nodes={UnitId(u["unit_id"]): u["centroid_node_id"] for u in units},
        groups=tuple(
            PopulationGroup(GroupId(g["group_id"]), g["name"], g["definition_rule"])
            for g in _rows(pkg, "tables/groups.csv")
        ),
        services=tuple(
            Service(ServiceId(s["service_id"]), s["name"], ServiceUnit(s["service_unit"]))
            for s in _rows(pkg, "tables/services.csv")
        ),
        facilities=tuple(
            Facility(
                FacilityId(f["facility_id"]),
                f["name"],
                f["facility_type"],
                frozenset(capacity.get(f["facility_id"], {})),
                capacity=capacity.get(f["facility_id"], {}),
            )
            for f in facilities
        ),
        facility_nodes={FacilityId(f["facility_id"]): f["node_id"] for f in facilities},
        facility_units={FacilityId(f["facility_id"]): UnitId(f["unit_id"]) for f in facilities},
        node_units={n["node_id"]: UnitId(n["unit_id"]) for n in nodes},
        edges=tuple(
            NetworkEdge(
                e["edge_id"],
                e["from_node_id"],
                e["to_node_id"],
                {
                    TransportMode.WALK: e["travel_time_walk_min"],
                    TransportMode.CAR: e["travel_time_car_min"],
                },
                bool(e["closable"]),  # BOOLEAN is stored as 0/1 in a GeoPackage
            )
            for e in _features(pkg, "network_edges")
        ),
        hand_checks=tuple(
            HandCheck(
                frozenset(filter(None, r["closed_edges"].split(";"))),
                TransportMode(r["mode"]),
                UnitId(r["unit_id"]),
                FacilityId(r["facility_id"]),
                float(r["travel_time_min"]),
            )
            for r in _rows(pkg, "checks/hand_check_travel_times.csv")
        ),
    )

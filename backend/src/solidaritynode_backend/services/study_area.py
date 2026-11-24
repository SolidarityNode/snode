"""Build a core :class:`~solidaritynode_core.model.StudyArea` from one stored data version.

Only features open in that version are handed to models: a feature is open when ``valid_to`` is
empty or after the package date (features are closed, never deleted; ADR 0013).
"""

from __future__ import annotations

from datetime import date
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
from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.orm import DataVersion

__all__ = ["is_open", "load_study_area"]

_MODE_COLUMNS = {
    TransportMode.WALK: "travel_time_walk_min",
    TransportMode.CAR: "travel_time_car_min",
}


def is_open(properties: dict[str, Any], on: date) -> bool:
    """Return whether a feature is open (not closed) on ``on``."""
    valid_to = properties.get("valid_to")
    return valid_to is None or date.fromisoformat(valid_to) > on


def _num(value: object) -> float | None:
    return None if value is None or value == "" else float(str(value))


def load_study_area(db: Session, data_version_id: int) -> StudyArea:
    """Read the study area of ``data_version_id`` (open features only)."""
    dv = db.get(DataVersion, data_version_id)
    if dv is None:
        raise KeyError(f"data version {data_version_id} not found")
    layers: dict[str, list[dict[str, Any]]] = {}
    for layer, props in db.execute(
        text(
            "SELECT layer, properties FROM data_features WHERE data_version_id = :dv "
            "ORDER BY layer, feature_id"
        ),
        {"dv": data_version_id},
    ):
        layers.setdefault(layer, []).append(props)
    records: dict[str, list[dict[str, Any]]] = {}
    for table, props in db.execute(
        text(
            "SELECT table_name, properties FROM data_records WHERE data_version_id = :dv "
            "ORDER BY table_name, row_no"
        ),
        {"dv": data_version_id},
    ):
        records.setdefault(table, []).append(props)

    units = [u for u in layers.get("spatial_units", []) if is_open(u, dv.created)]
    facilities = [f for f in layers.get("facilities", []) if is_open(f, dv.created)]
    nodes = [n for n in layers.get("network_nodes", []) if is_open(n, dv.created)]
    edges = [e for e in layers.get("network_edges", []) if is_open(e, dv.created)]

    def capacity(f: dict[str, Any]) -> dict[ServiceId, CapacityInputs]:
        return {
            ServiceId(sid): CapacityInputs(
                _num(c["places"]), _num(c["staff"]), _num(c["throughput"])
            )
            for sid, c in sorted(f.get("services", {}).items())
        }

    return StudyArea(
        package_id=dv.package_id,
        package_version=dv.version,
        units=tuple(
            SpatialUnit(
                UnitId(u["unit_id"]),
                population_by_group={
                    GroupId(g): float(n) for g, n in sorted(u.get("population", {}).items())
                },
            )
            for u in units
        ),
        unit_roles={UnitId(u["unit_id"]): u["role"] for u in units},
        unit_nodes={UnitId(u["unit_id"]): u["centroid_node_id"] for u in units},
        groups=tuple(
            PopulationGroup(GroupId(g["group_id"]), g["name"], g["definition_rule"])
            for g in records.get("groups", [])
        ),
        services=tuple(
            Service(ServiceId(s["service_id"]), s["name"], ServiceUnit(s["service_unit"]))
            for s in records.get("services", [])
        ),
        facilities=tuple(
            Facility(
                FacilityId(f["facility_id"]),
                f["name"],
                f["facility_type"],
                frozenset(capacity(f)),
                capacity=capacity(f),
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
                {m: float(e[c]) for m, c in _MODE_COLUMNS.items() if e.get(c) is not None},
                bool(e.get("closable", False)),
            )
            for e in edges
        ),
        hand_checks=tuple(
            HandCheck(
                frozenset(filter(None, str(r["closed_edges"]).split(";"))),
                TransportMode(r["mode"]),
                UnitId(r["unit_id"]),
                FacilityId(r["facility_id"]),
                float(r["travel_time_min"]),
            )
            for r in records.get("hand_checks", [])
        ),
    )

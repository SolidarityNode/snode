"""Study-area input container handed to registered models (Spec 00 §3, Study area, Data package).

A :class:`StudyArea` is the content of **one data package version** as the model sees it: core
and buffer units, groups, services, the facilities that are open in that version, the network
and the package's hand-check table. It is built by the caller (the backend reads it from the
database); ``core`` does no I/O. Buffer units are included so models can use cross-border
facilities and network; results are reported for core units only (OQ-28: whether buffer demand
competes for capacity is open).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from solidaritynode_core.model.entities import (
    Facility,
    PopulationGroup,
    Service,
    SpatialUnit,
    TransportMode,
)
from solidaritynode_core.model.ids import FacilityId, UnitId

__all__ = ["HandCheck", "NetworkEdge", "NodeId", "StudyArea", "UnitRole"]

type NodeId = str
"""Stable network node identifier (Spec 00 §3, Stable identifiers)."""

type UnitRole = Literal["core", "buffer"]
"""Role of a spatial unit in the study area (Spec 00 §3, OQ-28)."""


@dataclass(frozen=True, slots=True)
class NetworkEdge:
    """Undirected network edge with a travel time per transport mode (Spec 00 §3, Network).

    Attributes:
        id: Stable edge id, the same in every package version.
        from_node: Start node.
        to_node: End node.
        travel_time_min: Minutes to traverse the edge per mode; a missing mode means the edge
            cannot be used with that mode.
        closable: Whether scenarios may close it (data attribute; not enforced here).
    """

    id: str
    from_node: NodeId
    to_node: NodeId
    travel_time_min: Mapping[TransportMode, float]
    closable: bool = False

    def __post_init__(self) -> None:
        """Validate non-negative finite times and freeze the mapping."""
        for mode, minutes in self.travel_time_min.items():
            if not math.isfinite(minutes) or minutes < 0:
                raise ValueError(f"edge {self.id!r}: travel time for {mode} must be >= 0")
        object.__setattr__(self, "travel_time_min", MappingProxyType(dict(self.travel_time_min)))


@dataclass(frozen=True, slots=True)
class HandCheck:
    """One expected shortest travel time from the package's hand-check table (DP-002).

    Attributes:
        closed_edges: Edges closed when the time was derived (empty for the baseline).
        mode: Transport mode.
        unit: Origin unit (its centroid node).
        facility: Destination facility.
        travel_time_min: Expected minutes.
    """

    closed_edges: frozenset[str]
    mode: TransportMode
    unit: UnitId
    facility: FacilityId
    travel_time_min: float


@dataclass(frozen=True, slots=True)
class StudyArea:
    """Inputs of one data package version, as handed to a model (Spec 00 §3).

    Attributes:
        package_id: Data package id.
        package_version: Semantic version of the data package.
        units: Core and buffer spatial units with population by group.
        unit_roles: ``core`` or ``buffer`` per unit.
        unit_nodes: Network node of each unit's population centroid.
        groups: Population groups.
        services: Services.
        facilities: Facilities **open** in this version (closed ones are left out by the
            caller).
        facility_nodes: Network node each facility is reached at.
        facility_units: Spatial unit containing each facility.
        node_units: Spatial unit containing each network node.
        edges: Network edges.
        hand_checks: Expected travel times shipped with the package, if any.
    """

    package_id: str
    package_version: str
    units: tuple[SpatialUnit, ...]
    unit_roles: Mapping[UnitId, UnitRole]
    unit_nodes: Mapping[UnitId, NodeId]
    groups: tuple[PopulationGroup, ...]
    services: tuple[Service, ...]
    facilities: tuple[Facility, ...]
    facility_nodes: Mapping[FacilityId, NodeId]
    facility_units: Mapping[FacilityId, UnitId]
    node_units: Mapping[NodeId, UnitId]
    edges: tuple[NetworkEdge, ...]
    hand_checks: tuple[HandCheck, ...] = field(default=())

    def __post_init__(self) -> None:
        """Check that every unit and facility is placed on the network."""
        unit_ids = {u.id for u in self.units}
        if missing := unit_ids - set(self.unit_nodes):
            raise ValueError(f"units without a centroid node: {sorted(missing)}")
        if missing := unit_ids - set(self.unit_roles):
            raise ValueError(f"units without a role: {sorted(missing)}")
        facility_ids = {f.id for f in self.facilities}
        if lost := facility_ids - set(self.facility_nodes):
            raise ValueError(f"facilities without a network node: {sorted(lost)}")
        for name in ("unit_roles", "unit_nodes", "facility_nodes", "facility_units", "node_units"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def core_units(self) -> tuple[SpatialUnit, ...]:
        """Return the core units, the only ones results are reported for (OQ-28)."""
        return tuple(u for u in self.units if self.unit_roles[u.id] == "core")

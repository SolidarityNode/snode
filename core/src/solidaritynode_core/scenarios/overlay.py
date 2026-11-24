"""Apply a scenario overlay to the baseline study area (Spec 00 §3 Scenario; Paper 1 §13).

A scenario is a set of **changes relative to the baseline**, never a copy of the data. This
module applies only the mechanical part of the overlay:

* capacity changes change the named capacity **input** of a facility (absolute, or percent of
  the baseline input value). How inputs become capacity in service units is Paper 1 §7 and is
  not done here;
* new facilities are added to the study area at an existing network node;
* closed network edges are returned so a caller can remove them per mode;
* disruption severities ``DS_{f,c}`` are **recorded only**. How a severity changes functional
  capacity is a Paper 3 method (§7–10) and is not applied here.

It also checks references: every facility, service and edge a scenario names must exist in the
study area (stable ids, ADR 0013/0016). A reference to a closed or missing feature is reported,
never silently dropped.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from solidaritynode_core.model.entities import (
    CapacityChange,
    CapacityChangeMode,
    CapacityInputs,
    Facility,
    NewFacility,
    Scenario,
    TransportMode,
)
from solidaritynode_core.model.ids import FacilityId, ServiceId, UnitId
from solidaritynode_core.model.study_area import StudyArea

__all__ = [
    "FacilityChange",
    "OverlayResult",
    "ScenarioReferenceError",
    "apply_overlay",
    "check_references",
]


class ScenarioReferenceError(ValueError):
    """The scenario names features that are not in the study area, or cannot be applied."""

    def __init__(self, problems: list[str]) -> None:
        """Keep the list of problems."""
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class FacilityChange:
    """One change the overlay made to one facility.

    Attributes:
        facility: Facility id.
        unit: Spatial unit containing the facility.
        kind: ``capacity``, ``new`` or ``severity``.
        detail: Human-readable description, for example ``"S-HC staff 4 -> 5"``.
        services: Services the change concerns.
    """

    facility: FacilityId
    unit: UnitId | None
    kind: str
    detail: str
    services: frozenset[str]


@dataclass(frozen=True, slots=True)
class OverlayResult:
    """The baseline with the overlay applied.

    Attributes:
        area: Study area after capacity changes and new facilities.
        changes: Every facility change, in scenario order.
        closed_edges: Edges closed by the scenario.
        closed_modes: Modes for which those edges are closed.
    """

    area: StudyArea
    changes: tuple[FacilityChange, ...]
    closed_edges: frozenset[str]
    closed_modes: frozenset[TransportMode]


def check_references(area: StudyArea, scenario: Scenario) -> list[str]:
    """Return every reference problem of ``scenario`` against ``area`` (Spec 00 §3).

    Args:
        area: Study area of one data package version (open facilities only).
        scenario: The scenario overlay.

    Returns:
        Human-readable problems; empty when every reference resolves.
    """
    facilities = {f.id: f for f in area.facilities}
    nodes = set(area.node_units)
    edges = {e.id: e for e in area.edges}
    problems: list[str] = []
    new_ids: set[str] = set()
    for intervention in scenario.interventions:
        if isinstance(intervention, NewFacility):
            fid = intervention.facility.id
            if fid in facilities or fid in new_ids:
                problems.append(f"new facility {fid}: id already exists")
            if intervention.node_id is None or intervention.node_id not in nodes:
                problems.append(f"new facility {fid}: network node {intervention.node_id} missing")
            new_ids.add(fid)
    for intervention in scenario.interventions:
        if isinstance(intervention, CapacityChange):
            problems.extend(_capacity_problems(facilities, intervention))
    for fid in scenario.facility_severities:
        if fid not in facilities and fid not in new_ids:
            problems.append(f"facility {fid}: closed or missing in data {area.package_version}")
    if scenario.network_disruption is not None:
        for eid in sorted(scenario.network_disruption.affected_link_ids):
            if eid not in edges:
                problems.append(f"edge {eid}: closed or missing in data {area.package_version}")
            elif not edges[eid].closable:
                problems.append(f"edge {eid}: cannot be closed (closable = false)")
    return problems


def _capacity_problems(facilities: dict[FacilityId, Facility], change: CapacityChange) -> list[str]:
    facility = facilities.get(change.facility)
    if facility is None:
        return [f"facility {change.facility}: closed or missing in the data version"]
    inputs = facility.capacity.get(change.service)
    if inputs is None:
        return [f"facility {change.facility}: does not offer service {change.service}"]
    current = getattr(inputs, change.capacity_input)
    if current is None:
        return [f"facility {change.facility}: {change.capacity_input} is not set"]
    if _changed(current, change) < 0:
        return [f"facility {change.facility}: {change.capacity_input} would become negative"]
    return []


def _changed(current: float, change: CapacityChange) -> float:
    if change.mode is CapacityChangeMode.RELATIVE:
        return current * (1.0 + change.amount / 100.0)
    return current + change.amount


def apply_overlay(area: StudyArea, scenario: Scenario) -> OverlayResult:
    """Apply ``scenario`` to ``area`` (Spec 00 §3 Scenario; Paper 1 §13).

    Args:
        area: Baseline study area (one data package version).
        scenario: Overlay to apply.

    Returns:
        The changed study area and a record of every change. Severities are recorded, not
        applied (Paper 3 method).

    Raises:
        ScenarioReferenceError: If :func:`check_references` reports any problem.
    """
    if problems := check_references(area, scenario):
        raise ScenarioReferenceError(problems)
    facilities = {f.id: f for f in area.facilities}
    facility_nodes = dict(area.facility_nodes)
    facility_units = dict(area.facility_units)
    changes: list[FacilityChange] = []
    for intervention in scenario.interventions:
        if isinstance(intervention, NewFacility):
            new = intervention.facility
            node = str(intervention.node_id)
            facilities[new.id] = new
            facility_nodes[new.id] = node
            facility_units[new.id] = area.node_units[node]
            changes.append(
                FacilityChange(
                    new.id, facility_units[new.id], "new", f"new at {node}", new.services
                )
            )
    for intervention in scenario.interventions:
        if isinstance(intervention, CapacityChange):
            facility = facilities[intervention.facility]
            inputs = facility.capacity[intervention.service]
            before = float(getattr(inputs, intervention.capacity_input))
            after = _changed(before, intervention)
            new_inputs = dataclasses.replace(inputs, **{intervention.capacity_input: after})
            capacity: dict[ServiceId, CapacityInputs] = dict(facility.capacity)
            capacity[intervention.service] = new_inputs
            facilities[facility.id] = dataclasses.replace(facility, capacity=capacity)
            detail = f"{intervention.service} {intervention.capacity_input} {before:g} -> {after:g}"
            changes.append(
                FacilityChange(
                    facility.id,
                    facility_units.get(facility.id),
                    "capacity",
                    detail,
                    frozenset({intervention.service}),
                )
            )
    for fid, severity in scenario.facility_severities.items():
        changes.append(
            FacilityChange(
                fid,
                facility_units.get(fid),
                "severity",
                f"DS = {severity:g} (recorded only)",
                facilities[fid].services,
            )
        )
    disruption = scenario.network_disruption
    changed = dataclasses.replace(
        area,
        facilities=tuple(facilities.values()),
        facility_nodes=facility_nodes,
        facility_units=facility_units,
    )
    return OverlayResult(
        area=changed,
        changes=tuple(changes),
        closed_edges=frozenset(disruption.affected_link_ids) if disruption else frozenset(),
        closed_modes=frozenset(disruption.modes) if disruption else frozenset(),
    )

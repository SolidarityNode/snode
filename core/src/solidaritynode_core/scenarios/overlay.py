"""Apply a scenario overlay to the baseline study area (Spec 00 §3 Scenario; Paper 1 §13).

A scenario is a set of **changes relative to the baseline**, never a copy of the data. This
module applies only the mechanical part of the overlay:

* capacity changes change the named capacity **input** of a facility (absolute, or percent of
  the baseline input value). How inputs become capacity in service units is Paper 1 §7 and is
  not done here;
* new facilities are added to the study area at an existing network node;
* edge changes (travel time or speed), new edges and population changes (Paper 1 §13, §15.7)
  are checked and **recorded only**: they are placeholders without behaviour;
* closed network edges are returned so a caller can remove them per mode;
* disruption severities ``DS_{f,c}`` are **recorded only**. How a severity changes functional
  capacity is a Paper 3 method (§7–10) and is not applied here.

**Order of application** (ADR 0016; OQ-30, a proposed default that touches the method and must
be confirmed when the Paper 3 spec is written): first the interventions, in the order new
facilities, capacity changes, network changes (edge changes, then new edges), population
changes; then the disruptions, severities and closed edges, which may also hit the new
facilities and new edges of the same scenario.

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
    ChangeMode,
    EdgeChange,
    EdgeQuantity,
    Facility,
    NewEdge,
    NewFacility,
    PopulationChange,
    Scenario,
    TransportMode,
)
from solidaritynode_core.model.ids import FacilityId, ServiceId, UnitId
from solidaritynode_core.model.study_area import NetworkEdge, StudyArea

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
        recorded: Interventions recorded but not applied (edge changes, new edges, population
            changes), as human-readable lines in application order, followed by a line for each
            new edge the scenario also closes (added, then closed: no net effect, OQ-30).
    """

    area: StudyArea
    changes: tuple[FacilityChange, ...]
    closed_edges: frozenset[str]
    closed_modes: frozenset[TransportMode]
    recorded: tuple[str, ...] = ()


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
    new_edges: dict[str, NewEdge] = {}
    for intervention in scenario.interventions:
        if isinstance(intervention, NewEdge):
            if intervention.id in edges or intervention.id in new_edges:
                problems.append(f"new edge {intervention.id}: id already exists")
            for node in (intervention.from_node, intervention.to_node):
                if node not in nodes:
                    problems.append(f"new edge {intervention.id}: network node {node} missing")
            new_edges[intervention.id] = intervention
    for intervention in scenario.interventions:
        if isinstance(intervention, EdgeChange):
            problems.extend(_edge_problems(edges, new_edges, intervention, area.package_version))
        elif isinstance(intervention, PopulationChange):
            problems.extend(_population_problems(area, intervention))
    # Disruptions come after the interventions, so they may hit new facilities and new edges.
    for fid in scenario.facility_severities:
        if fid not in facilities and fid not in new_ids:
            problems.append(f"facility {fid}: closed or missing in data {area.package_version}")
    if scenario.network_disruption is not None:
        for eid in sorted(scenario.network_disruption.affected_link_ids):
            closable = (
                edges[eid].closable
                if eid in edges
                else new_edges[eid].closable
                if eid in new_edges
                else None
            )
            if closable is None:
                problems.append(f"edge {eid}: closed or missing in data {area.package_version}")
            elif not closable:
                problems.append(f"edge {eid}: cannot be closed (closable = false)")
    return problems


def _edge_problems(
    edges: dict[str, NetworkEdge], new: dict[str, NewEdge], change: EdgeChange, version: str
) -> list[str]:
    times = (
        edges[change.edge].travel_time_min
        if change.edge in edges
        else new[change.edge].travel_time_min
        if change.edge in new
        else None
    )
    if times is None:
        return [f"edge {change.edge}: closed or missing in data {version}"]
    if change.mode not in times:
        return [f"edge {change.edge}: has no {change.mode} travel time to change"]
    if (
        change.quantity is EdgeQuantity.TRAVEL_TIME
        and change.change is ChangeMode.ABSOLUTE
        and times[change.mode] + change.amount <= 0
    ):
        return [
            f"edge {change.edge}: {change.mode} travel time would not stay positive; "
            "to close a road use closed edges"
        ]
    # An absolute speed change cannot be checked here: edges carry travel times, not speeds.
    return []


def _population_problems(area: StudyArea, change: PopulationChange) -> list[str]:
    units = {u.id: u for u in area.units}
    unit = units.get(change.unit)
    if unit is None:
        return [f"unit {change.unit}: missing in data {area.package_version}"]
    if change.group not in {g.id for g in area.groups}:
        return [f"group {change.group}: missing in data {area.package_version}"]
    current = unit.population_by_group.get(change.group, 0.0)
    after = (
        current * (1.0 + change.amount / 100.0)
        if change.change is ChangeMode.RELATIVE
        else current + change.amount
    )
    if after < 0:
        return [f"unit {change.unit}, group {change.group}: population would become negative"]
    return []


def _recorded(intervention: EdgeChange | NewEdge | PopulationChange) -> str:
    def amount(change: ChangeMode, value: float, unit: str) -> str:
        return f"{value:+g} %" if change is ChangeMode.RELATIVE else f"{value:+g} {unit}"

    if isinstance(intervention, EdgeChange):
        unit = "min" if intervention.quantity is EdgeQuantity.TRAVEL_TIME else "km/h"
        return (
            f"edge {intervention.edge} {intervention.mode} {intervention.quantity} "
            f"{amount(intervention.change, intervention.amount, unit)} (recorded only)"
        )
    if isinstance(intervention, NewEdge):
        times = ", ".join(f"{m} {t:g} min" for m, t in sorted(intervention.travel_time_min.items()))
        return (
            f"new edge {intervention.id} {intervention.from_node}-{intervention.to_node} "
            f"({times}) (recorded only)"
        )
    return (
        f"unit {intervention.unit} group {intervention.group} population "
        f"{amount(intervention.change, intervention.amount, 'persons')} (recorded only)"
    )


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
        The changed study area and a record of every change, in the order of application
        (module docstring; OQ-30 proposed). Severities, edge changes, new edges and population
        changes are recorded, not applied.

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
    recorded = [
        _recorded(i)
        for kind in (EdgeChange, NewEdge, PopulationChange)
        for i in scenario.interventions
        if isinstance(i, kind)
    ]
    disruption = scenario.network_disruption
    new_edges = {i.id for i in scenario.interventions if isinstance(i, NewEdge)}
    for eid in sorted(set(disruption.affected_link_ids) & new_edges if disruption else ()):
        # Interventions before disruptions (OQ-30): the edge is added, then closed. Reported so
        # it is never ignored silently.
        recorded.append(
            f"new edge {eid} is closed by the same scenario: added, then closed, "
            "so no net effect (OQ-30)"
        )
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
        recorded=tuple(recorded),
    )

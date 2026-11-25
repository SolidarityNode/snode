"""Scenario overlay JSON (ADR 0016, accepted for v0.1, to be revisited).

A scenario is a set of **changes relative to the baseline** (Spec 00 §3): capacity changes
(absolute or percent), new facilities, network changes (travel time or speed per edge and mode,
new edges) and population changes (Paper 1 §13, §15.7; placeholders, recorded only), facility
disruption severities ``DS ∈ [0, 1]`` (Paper 3), closed network edges, the rationing case
(OQ-24) and the reference-scenario flag (OQ-16). Interventions are applied before disruptions
(ADR 0016; OQ-30, proposed).
Features are referred to by their stable ids from the data package (ADR 0013).

The JSON Schema of :class:`ScenarioBody` is exported to ``docs/schemas/scenario.schema.json``
(``make schemas``) and a test keeps it current.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from solidaritynode_core.model import (
    CapacityChange,
    CapacityChangeMode,
    CapacityInputs,
    ChangeMode,
    EdgeChange,
    EdgeQuantity,
    Facility,
    FacilityId,
    GroupId,
    Intervention,
    NetworkDisruption,
    NewEdge,
    NewFacility,
    PopulationChange,
    Rationing,
    ReferenceScenarioLevel,
    Scenario,
    ScenarioId,
    ScenarioKind,
    ServiceId,
    TransportMode,
    UnitId,
)

__all__ = [
    "SCENARIO_SCHEMA_VERSION",
    "CapacityChangeIn",
    "EdgeChangeIn",
    "NetworkChangesIn",
    "NetworkClosureIn",
    "NewEdgeIn",
    "NewFacilityIn",
    "PopulationChangeIn",
    "ScenarioBody",
    "ServiceCapacityIn",
    "SeverityIn",
    "export_json_schema",
]

SCENARIO_SCHEMA_VERSION = "1.0"

_ID = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapacityChangeIn(_Strict):
    """Change one capacity input of an existing facility (Paper 1 §13)."""

    facility_id: str = _ID
    service_id: str = _ID
    capacity_input: Literal["places", "staff", "throughput"]
    mode: Literal["absolute", "relative"] = Field(
        description="absolute: in the input's own unit; relative: percent of the baseline value"
    )
    amount: float = Field(allow_inf_nan=False, description="Signed change")


class ServiceCapacityIn(_Strict):
    """Capacity inputs of a new facility for one service."""

    service_id: str = _ID
    places: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    staff: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    throughput: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class NewFacilityIn(_Strict):
    """Add a facility that is not in the baseline, at an existing network node (Paper 1 §13)."""

    facility_id: str = _ID
    name: str = Field(min_length=1, max_length=200)
    facility_type: str = Field(min_length=1, max_length=64)
    node_id: str = _ID
    services: list[ServiceCapacityIn] = Field(min_length=1)


Mode = Literal["walk", "car", "public_transport"]


class EdgeChangeIn(_Strict):
    """Change the travel time or speed of one edge for one mode (Paper 1 §13, §15.7).

    A placeholder: checked and recorded, not applied yet.
    """

    edge_id: str = _ID
    mode: Mode
    quantity: Literal["travel_time", "speed"]
    change: Literal["absolute", "relative"] = Field(
        description="absolute: minutes (travel time) or km/h (speed); relative: percent"
    )
    amount: float = Field(allow_inf_nan=False, description="Signed change")


class NewEdgeIn(_Strict):
    """A new network edge between two existing nodes (Paper 1 §13, §15.7; placeholder)."""

    edge_id: str = _ID
    from_node_id: str = _ID
    to_node_id: str = _ID
    travel_time_min: dict[Mode, float] = Field(
        min_length=1, description="Minutes to traverse the edge per mode (>= 0)"
    )
    closable: bool = Field(default=True, description="Whether disruptions may close it")


class NetworkChangesIn(_Strict):
    """Network interventions: edge changes and new edges (placeholders, recorded only)."""

    edge_changes: list[EdgeChangeIn] = Field(default_factory=list)
    new_edges: list[NewEdgeIn] = Field(default_factory=list)


class PopulationChangeIn(_Strict):
    """Change the population of one group in one unit (Paper 1 §13, §15.7; placeholder)."""

    unit_id: str = _ID
    group_id: str = _ID
    change: Literal["absolute", "relative"] = Field(
        description="absolute: persons; relative: percent of the baseline count"
    )
    amount: float = Field(allow_inf_nan=False, description="Signed change")


class SeverityIn(_Strict):
    """Disruption severity ``DS_{f,c}`` of one facility (Paper 3 §7–10)."""

    facility_id: str = _ID
    severity: float = Field(ge=0, le=1, allow_inf_nan=False)


class NetworkClosureIn(_Strict):
    """Network edges closed for the given modes (Paper 3 §9)."""

    edge_ids: list[str] = Field(min_length=1)
    modes: list[Literal["walk", "car", "public_transport"]] = Field(min_length=1)


class ScenarioBody(_Strict):
    """The overlay of one scenario version (Spec 00 §3; ADR 0016).

    ``reference_level`` is the reference-scenario flag: ``null`` for an ordinary scenario, or
    the standardised level it stands for (OQ-16; how reference scenarios are constructed is
    open). Disruption scenarios (any severity or closed edge) must state a ``rationing`` case
    (OQ-24). ``network_changes`` and ``population_changes`` are placeholders: validated against
    the data and recorded on runs, without behaviour yet. Order of application: interventions,
    then disruptions (ADR 0016; OQ-30, proposed).
    """

    schema_version: Literal["1.0"] = "1.0"
    capacity_changes: list[CapacityChangeIn] = Field(default_factory=list)
    new_facilities: list[NewFacilityIn] = Field(default_factory=list)
    network_changes: NetworkChangesIn = Field(default_factory=NetworkChangesIn)
    population_changes: list[PopulationChangeIn] = Field(default_factory=list)
    severities: list[SeverityIn] = Field(default_factory=list)
    closed_edges: NetworkClosureIn | None = None
    rationing: Literal["uniform", "concentrated"] | None = None
    reference_level: Literal["minor", "moderate", "severe"] | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        def dupes(values: list[Any]) -> list[str]:
            return sorted({str(v) for v in values if values.count(v) > 1})

        if d := dupes([s.facility_id for s in self.severities]):
            raise ValueError(f"severity given twice for facility {', '.join(d)}")
        if d := dupes([f.facility_id for f in self.new_facilities]):
            raise ValueError(f"new facility id used twice: {', '.join(d)}")
        if self.closed_edges and (d := dupes(self.closed_edges.edge_ids)):
            raise ValueError(f"edge closed twice: {', '.join(d)}")
        net = self.network_changes
        if d := dupes([(c.edge_id, c.mode, c.quantity) for c in net.edge_changes]):
            raise ValueError(f"the same edge, mode and quantity changed twice: {', '.join(d)}")
        if d := dupes([e.edge_id for e in net.new_edges]):
            raise ValueError(f"new edge id used twice: {', '.join(d)}")
        if d := dupes([(p.unit_id, p.group_id) for p in self.population_changes]):
            raise ValueError(f"population of the same unit and group changed twice: {', '.join(d)}")
        self.to_core("validation", "validation")  # core rules (OQ-16, OQ-24) -> 422
        return self

    @property
    def is_disruption(self) -> bool:
        """Return whether the overlay disrupts facilities or the network (Paper 3)."""
        return bool(self.severities or self.closed_edges)

    def to_core(self, scenario_id: str, name: str, description: str = "") -> Scenario:
        """Convert to :class:`solidaritynode_core.model.Scenario`.

        Raises:
            ValueError: If a core rule fails (for example a disruption without a rationing case,
                OQ-24, or a reference level on a counterfactual scenario, OQ-16).
        """
        interventions: list[Intervention] = [
            CapacityChange(
                FacilityId(c.facility_id),
                ServiceId(c.service_id),
                c.capacity_input,
                CapacityChangeMode(c.mode),
                c.amount,
            )
            for c in self.capacity_changes
        ]
        for f in self.new_facilities:
            capacity = {
                ServiceId(s.service_id): CapacityInputs(s.places, s.staff, s.throughput)
                for s in f.services
            }
            facility = Facility(
                FacilityId(f.facility_id),
                f.name,
                f.facility_type,
                frozenset(capacity),
                capacity=capacity,
            )
            interventions.append(NewFacility(facility, node_id=f.node_id))
        interventions.extend(
            EdgeChange(
                c.edge_id,
                TransportMode(c.mode),
                EdgeQuantity(c.quantity),
                ChangeMode(c.change),
                c.amount,
            )
            for c in self.network_changes.edge_changes
        )
        interventions.extend(
            NewEdge(
                e.edge_id,
                e.from_node_id,
                e.to_node_id,
                {TransportMode(m): t for m, t in e.travel_time_min.items()},
                e.closable,
            )
            for e in self.network_changes.new_edges
        )
        interventions.extend(
            PopulationChange(UnitId(p.unit_id), GroupId(p.group_id), ChangeMode(p.change), p.amount)
            for p in self.population_changes
        )
        closure = None
        if self.closed_edges:
            closure = NetworkDisruption(
                frozenset(TransportMode(m) for m in self.closed_edges.modes),
                frozenset(self.closed_edges.edge_ids),
            )
        try:
            return Scenario(
                id=ScenarioId(scenario_id),
                name=name,
                kind=ScenarioKind.DISRUPTION if self.is_disruption else ScenarioKind.COUNTERFACTUAL,
                facility_severities={
                    FacilityId(s.facility_id): s.severity for s in self.severities
                },
                network_disruption=closure,
                interventions=tuple(interventions),
                rationing=Rationing(self.rationing) if self.rationing else None,
                reference_level=(
                    ReferenceScenarioLevel(self.reference_level) if self.reference_level else None
                ),
                description=description,
            )
        except ValueError as exc:
            message = str(exc)
            if "reference scenarios" in message:
                message += ": add a severity or a closed edge, or clear the reference level"
            raise ValueError(message) from exc


def export_json_schema(path: Path) -> None:
    """Write the JSON Schema of :class:`ScenarioBody` to ``path``."""
    schema = ScenarioBody.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:solidaritynode:schema:scenario:1.0"
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")

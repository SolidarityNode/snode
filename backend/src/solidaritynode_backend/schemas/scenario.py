"""Scenario overlay JSON (ADR 0016, accepted for v0.1, to be revisited).

A scenario is a set of **changes relative to the baseline** (Spec 00 §3): capacity changes
(absolute or percent), new facilities, facility disruption severities ``DS ∈ [0, 1]`` (Paper 3),
closed network edges, the rationing case (OQ-24) and the reference-scenario flag (OQ-16).
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
    Facility,
    FacilityId,
    NetworkDisruption,
    NewFacility,
    Rationing,
    ReferenceScenarioLevel,
    Scenario,
    ScenarioId,
    ScenarioKind,
    ServiceId,
    TransportMode,
)

__all__ = [
    "SCENARIO_SCHEMA_VERSION",
    "CapacityChangeIn",
    "NetworkClosureIn",
    "NewFacilityIn",
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
    (OQ-24).
    """

    schema_version: Literal["1.0"] = "1.0"
    capacity_changes: list[CapacityChangeIn] = Field(default_factory=list)
    new_facilities: list[NewFacilityIn] = Field(default_factory=list)
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
        interventions: list[CapacityChange | NewFacility] = [
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

"""Immutable domain entities (Spec 00 §3).

Entities hold inputs and identifiers only. They contain no methodology: how accessibility,
capacity, need or vulnerability are computed from them belongs to the modules and is partly
open (see ``docs/specs/open-questions.md``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from solidaritynode_core.model.ids import FacilityId, GroupId, ScenarioId, ServiceId, UnitId
from solidaritynode_core.model.quantity import ServiceUnit
from solidaritynode_core.model.uncertain import Uncertain

__all__ = [
    "CapacityChange",
    "CapacityChangeMode",
    "CapacityInputs",
    "Facility",
    "FacilityFunctionalState",
    "GeoInterface",
    "GroupProfiles",
    "Intervention",
    "NetworkDisruption",
    "NewFacility",
    "PopulationGroup",
    "Rationing",
    "ReferenceScenarioLevel",
    "Scenario",
    "ScenarioKind",
    "Service",
    "SpatialUnit",
    "TransportMode",
]


@runtime_checkable
class GeoInterface(Protocol):
    """Any geometry exposing the ``__geo_interface__`` protocol (for example Shapely objects).

    Keeps ``core`` free of a hard dependency on a geometry library at this stage (ADR 0003).
    """

    @property
    def __geo_interface__(self) -> Mapping[str, Any]:
        """Return a GeoJSON-like mapping."""
        ...


def _freeze[K, V](mapping: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(mapping))


# ---------------------------------------------------------------------------------------------
# Spatial units and groups
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpatialUnit:
    """Spatial unit ``i`` (Spec 00 §3; Paper 1 §4; OQ-1, OQ-22).

    Demand, supply and gap belong to the spatial unit (OQ-1). The code stays generic; the first
    application uses the Greek Local Community (ΤΚ).

    Attributes:
        id: Unit identifier.
        geometry: Unit geometry (any ``__geo_interface__`` object), or ``None`` when only
            attributes are used.
        population_by_group: Persons per group (Paper 1 §4, ELSTAT; ``INPUT``, unit × group).
            Groups may overlap (OQ-6, open), so these counts must not be summed across groups
            to get the unit population.
    """

    id: UnitId
    geometry: GeoInterface | None = None
    population_by_group: Mapping[GroupId, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate non-negative finite populations and freeze the mapping."""
        for group, count in self.population_by_group.items():
            if not math.isfinite(count) or count < 0:
                raise ValueError(f"population of group {group!r} must be finite and >= 0")
        object.__setattr__(self, "population_by_group", _freeze(self.population_by_group))


@dataclass(frozen=True, slots=True)
class GroupProfiles:
    """The three descriptive profiles of a population group (Spec 00 §3; Paper 1 §4).

    Content and sources are open (OQ-6). They are kept as free-text descriptions until the
    group definitions are specified.

    Attributes:
        demographic: How many people belong to the group.
        mobility: How the group can travel (relates to transport modes, OQ-5).
        demand: How likely the group is to use the service (visible use, OQ-8).
    """

    demographic: str = ""
    mobility: str = ""
    demand: str = ""


@dataclass(frozen=True, slots=True)
class PopulationGroup:
    """Population group ``g`` (Spec 00 §3; Paper 1 §4; Paper 2 §7).

    A group says **who is examined**; it is not a measure of need and not a measure of social
    susceptibility (CLAUDE.md invariants 4 and 5). Groups may overlap (OQ-6, open).

    Attributes:
        id: Group identifier.
        name: Display name (terminology: OQ-22).
        definition_rule: Human-readable rule, for example ``"Age >= 65"`` (thresholds: OQ-6).
        definition_indicators: Names of indicators used in the definition. They must never be
            reused as Social Susceptibility evidence (Paper 2 §7, OQ-9); see
            :meth:`check_susceptibility_indicators`.
        profiles: Demographic, mobility and demand profiles.
    """

    id: GroupId
    name: str
    definition_rule: str
    definition_indicators: frozenset[str] = frozenset()
    profiles: GroupProfiles = field(default_factory=GroupProfiles)

    def check_susceptibility_indicators(self, indicators: frozenset[str]) -> None:
        """Enforce Paper 2 §7 / OQ-9: no group-definition indicator is reused as evidence.

        Args:
            indicators: Indicator names proposed as Social Susceptibility evidence for this
                group (for any service).

        Raises:
            ValueError: If any indicator is also a definition indicator of the group.
        """
        reused = indicators & self.definition_indicators
        if reused:
            raise ValueError(
                f"indicators {sorted(reused)} define group {self.id!r} and cannot be reused as "
                "Social Susceptibility evidence (Paper 2 §7, OQ-9)"
            )


# ---------------------------------------------------------------------------------------------
# Services, facilities and transport
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Service:
    """Service ``s`` (Spec 00 §3; OQ-24 decided; OQ-26 approach decided, values open).

    Attributes:
        id: Service identifier.
        name: Display name.
        unit: The service unit in which need and capacity are measured (OQ-24).
        max_acceptable_wait: Maximum acceptable waiting time; a request not fulfilled within it
            counts as unmet need (OQ-26). The value is set with domain experts in
            configuration, never in code; ``None`` means "not yet set". Whether it differs by
            group is open (OQ-26).
    """

    id: ServiceId
    name: str
    unit: ServiceUnit
    max_acceptable_wait: timedelta | None = None

    def __post_init__(self) -> None:
        """Validate that a configured waiting time is positive."""
        if self.max_acceptable_wait is not None and self.max_acceptable_wait <= timedelta(0):
            raise ValueError("max_acceptable_wait must be positive")


class TransportMode(StrEnum):
    """Transport mode ``m`` (Spec 00 §2; Paper 1 §3.4). Combination of modes: OQ-5 (open)."""

    WALK = "walk"
    PUBLIC_TRANSPORT = "public_transport"
    CAR = "car"


@dataclass(frozen=True, slots=True)
class CapacityInputs:
    """Inputs to physical capacity ``C_f^physical`` (Paper 1 §7).

    How these inputs combine into capacity in service units is not specified here.

    Attributes:
        places: Places or beds, if relevant.
        staff: Staff (for example full-time equivalents).
        throughput: Service units the facility can deliver per reference period, if known.
    """

    places: float | None = None
    staff: float | None = None
    throughput: float | None = None

    def __post_init__(self) -> None:
        """Validate that given inputs are finite and non-negative."""
        for name in ("places", "staff", "throughput"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and >= 0")


class FacilityFunctionalState(StrEnum):
    """Facility functional state (Paper 4 §5; Spec 00 §4.4).

    Cycle: Normal → Under Pressure → Degraded → Critical → Recovering → Normal. How the state
    is derived from operational indicators (rules or learned) is open (OQ-17).
    """

    NORMAL = "normal"
    UNDER_PRESSURE = "under_pressure"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    RECOVERING = "recovering"


@dataclass(frozen=True, slots=True)
class Facility:
    """Facility ``f`` (Spec 00 §3; Paper 1 §7).

    A facility's state is never automatically a spatial unit's service loss (CLAUDE.md
    invariant 3): coverage is computed at the network level.

    Attributes:
        id: Facility identifier.
        name: Display name.
        facility_type: Type label (for example ``"health_centre"``).
        services: Services offered.
        location: Location geometry, or ``None``.
        capacity: Inputs to physical capacity, per service.
        operating_hours: Free-text opening hours, if known.
        availability: Availability of the facility (``PARAMETER``, Paper 1 §7), uncertain.
    """

    id: FacilityId
    name: str
    facility_type: str
    services: frozenset[ServiceId]
    location: GeoInterface | None = None
    capacity: Mapping[ServiceId, CapacityInputs] = field(default_factory=dict)
    operating_hours: str | None = None
    availability: Uncertain | None = None

    def __post_init__(self) -> None:
        """Validate that capacity is given only for offered services; freeze the mapping."""
        unknown = set(self.capacity) - set(self.services)
        if unknown:
            raise ValueError(f"capacity given for services not offered: {sorted(unknown)}")
        object.__setattr__(self, "capacity", _freeze(self.capacity))


# ---------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------


class ScenarioKind(StrEnum):
    """Kind of scenario ``c`` (Paper 1 §13; Paper 3 §7–10). One engine serves both (Spec 00 §5)."""

    COUNTERFACTUAL = "counterfactual"
    DISRUPTION = "disruption"


class Rationing(StrEnum):
    """How a shortage is spread among people: two bounding cases (OQ-24 decided).

    Attributes:
        UNIFORM: Everyone receives proportionally less.
        CONCENTRATED: Some are fully served, others not at all.
    """

    UNIFORM = "uniform"
    CONCENTRATED = "concentrated"


class ReferenceScenarioLevel(StrEnum):
    """Standardised reference scenario at which vulnerability is mapped (OQ-16 decided).

    How each level is constructed (which severities, which facilities) is not defined here.
    """

    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class NetworkDisruption:
    """Optional disruption of a transport network (Paper 3 §9).

    The representation of network links is provisional until the network data model is
    specified (ADR 0009, geospatial data sources).

    Attributes:
        modes: Transport modes whose network is disrupted.
        affected_link_ids: Identifiers of affected network links.
        description: Free-text description.
    """

    modes: frozenset[TransportMode]
    affected_link_ids: frozenset[str] = frozenset()
    description: str = ""


class CapacityChangeMode(StrEnum):
    """How a capacity change is expressed (Paper 1 §13; Spec 00 §3).

    Attributes:
        ABSOLUTE: ``amount`` is in the capacity input's own unit (for example places or staff).
        RELATIVE: ``amount`` is a percentage of the baseline value (for example ``20`` for +20 %).
    """

    ABSOLUTE = "absolute"
    RELATIVE = "relative"


@dataclass(frozen=True, slots=True)
class CapacityChange:
    """What-if intervention: change one capacity input of a facility (Paper 1 §13; Spec 00 §3).

    A typed placeholder only. It records the change relative to the baseline (a scenario is an
    overlay, never a copy of the data); how it is applied to capacity and supply is not
    implemented here.

    Attributes:
        facility: Facility ``f`` whose capacity changes.
        service: Service ``s`` the change applies to.
        capacity_input: Name of the capacity input (a field of :class:`CapacityInputs`, for
            example ``"staff"``).
        mode: Absolute or relative change.
        amount: Signed change (absolute units, or percent for relative changes).
    """

    facility: FacilityId
    service: ServiceId
    capacity_input: str
    mode: CapacityChangeMode
    amount: float

    def __post_init__(self) -> None:
        """Check that the input name exists and the amount is finite."""
        if self.capacity_input not in CapacityInputs.__dataclass_fields__:
            raise ValueError(f"unknown capacity input {self.capacity_input!r}")
        if not math.isfinite(self.amount):
            raise ValueError("capacity change amount must be finite")


@dataclass(frozen=True, slots=True)
class NewFacility:
    """What-if intervention: add a facility that is not in the baseline (Paper 1 §13; Spec 00 §3).

    A typed placeholder only; no behaviour.

    Attributes:
        facility: The facility to add. Its id must not exist in the baseline (checked when the
            scenario is applied, not here).
    """

    facility: Facility


type Intervention = CapacityChange | NewFacility
"""A what-if intervention of a counterfactual scenario (Paper 1 §13; Spec 00 §3)."""


@dataclass(frozen=True, slots=True)
class Scenario:
    """Scenario ``c`` (Paper 1 §13; Paper 3 §7–10; Spec 00 §3).

    Disruption severities ``DS_{f,c}`` are **scenario parameters**, not BN nodes (Spec 00
    §4.3). Examples of severity levels: 0 none, 0.25 minor, 0.5 moderate, 0.75 severe,
    1 complete.

    Attributes:
        id: Scenario identifier.
        name: Display name.
        kind: Counterfactual (Paper 1 §13) or disruption (Paper 3).
        facility_severities: ``DS_{f,c}`` in ``[0, 1]`` per affected facility; facilities not
            listed are undisrupted.
        network_disruption: Optional network disruption.
        interventions: What-if interventions relative to the baseline (Paper 1 §13). Typed
            placeholders without behaviour. Whether disruption scenarios may also carry
            interventions is not specified; no rule is enforced.
        rationing: Rationing case (OQ-24); required for disruption scenarios.
        reference_level: Set when this is a standardised reference scenario (OQ-16).
        description: Free-text description.
    """

    id: ScenarioId
    name: str
    kind: ScenarioKind
    facility_severities: Mapping[FacilityId, float] = field(default_factory=dict)
    network_disruption: NetworkDisruption | None = None
    interventions: tuple[Intervention, ...] = ()
    rationing: Rationing | None = None
    reference_level: ReferenceScenarioLevel | None = None
    description: str = ""

    def __post_init__(self) -> None:
        """Validate severity bounds and required fields; freeze mapping and interventions."""
        for facility, severity in self.facility_severities.items():
            if not math.isfinite(severity) or not 0.0 <= severity <= 1.0:
                raise ValueError(
                    f"disruption severity of facility {facility!r} must be in [0, 1], "
                    f"got {severity}"
                )
        if self.kind is ScenarioKind.DISRUPTION and self.rationing is None:
            raise ValueError("a disruption scenario must state its rationing case (OQ-24)")
        if self.reference_level is not None and self.kind is not ScenarioKind.DISRUPTION:
            raise ValueError("reference scenarios are disruption scenarios (OQ-16)")
        object.__setattr__(self, "facility_severities", _freeze(self.facility_severities))
        object.__setattr__(self, "interventions", tuple(self.interventions))

    @property
    def is_reference(self) -> bool:
        """Return whether this is a standardised reference scenario (OQ-16)."""
        return self.reference_level is not None

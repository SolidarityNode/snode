"""Domain model: entities, notation and the unit-of-analysis container (Papers 1–4; Spec 00 §2–4).

Public API:

* Notation: :class:`Dim`, :data:`UNIT_OF_ANALYSIS` (OQ-1).
* Identifiers: :data:`UnitId`, :data:`FacilityId`, :data:`GroupId`, :data:`ServiceId`,
  :data:`ScenarioId`.
* Entities (Spec 00 §3): :class:`SpatialUnit`, :class:`PopulationGroup`, :class:`Service`,
  :class:`Facility`, :class:`TransportMode`, :class:`Scenario`, :class:`Ticket`,
  :class:`RecordingCoverage`, :class:`RecoveryTrajectory`.
* Values: :class:`IndexedValues` (Paper 4 §3, ADR 0003), :data:`Uncertain`,
  :class:`LevelLMH`, :class:`ServiceQuantity` (OQ-24, OQ-25).
* Variable catalogue (Spec 00 §4): :data:`CATALOGUE`, :class:`VariableKind`.
"""

from solidaritynode_core.model.catalogue import (
    CATALOGUE,
    VariableKind,
    VariableSpec,
    variables_of_kind,
)
from solidaritynode_core.model.entities import (
    CapacityInputs,
    Facility,
    FacilityFunctionalState,
    GeoInterface,
    GroupProfiles,
    NetworkDisruption,
    PopulationGroup,
    Rationing,
    ReferenceScenarioLevel,
    Scenario,
    ScenarioKind,
    Service,
    SpatialUnit,
    TransportMode,
)
from solidaritynode_core.model.ids import FacilityId, GroupId, ScenarioId, ServiceId, UnitId
from solidaritynode_core.model.indexed import DimensionMismatchError, IndexedValues
from solidaritynode_core.model.notation import UNIT_OF_ANALYSIS, Dim
from solidaritynode_core.model.ordinal import LevelLMH
from solidaritynode_core.model.quantity import (
    ReferencePeriod,
    ServiceQuantity,
    ServiceUnit,
    UnitMismatchError,
)
from solidaritynode_core.model.tickets import TICKET_FIELDS, Period, RecordingCoverage, Ticket
from solidaritynode_core.model.trajectory import RecoveryTrajectory, TrajectoryKind
from solidaritynode_core.model.uncertain import (
    DiscreteDistribution,
    PointValue,
    Samples,
    Uncertain,
)

__all__ = [
    "CATALOGUE",
    "TICKET_FIELDS",
    "UNIT_OF_ANALYSIS",
    "CapacityInputs",
    "Dim",
    "DimensionMismatchError",
    "DiscreteDistribution",
    "Facility",
    "FacilityFunctionalState",
    "FacilityId",
    "GeoInterface",
    "GroupId",
    "GroupProfiles",
    "IndexedValues",
    "LevelLMH",
    "NetworkDisruption",
    "Period",
    "PointValue",
    "PopulationGroup",
    "Rationing",
    "RecordingCoverage",
    "RecoveryTrajectory",
    "ReferencePeriod",
    "ReferenceScenarioLevel",
    "Samples",
    "Scenario",
    "ScenarioId",
    "ScenarioKind",
    "Service",
    "ServiceId",
    "ServiceQuantity",
    "ServiceUnit",
    "SpatialUnit",
    "Ticket",
    "TrajectoryKind",
    "TransportMode",
    "Uncertain",
    "UnitId",
    "UnitMismatchError",
    "VariableKind",
    "VariableSpec",
    "variables_of_kind",
]

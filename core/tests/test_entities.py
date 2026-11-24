"""Invariants of the domain entities (Spec 00 §3)."""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from solidaritynode_core.model import (
    CapacityChange,
    CapacityChangeMode,
    CapacityInputs,
    Facility,
    FacilityId,
    NewFacility,
    Rationing,
    ReferenceScenarioLevel,
    Scenario,
    ScenarioId,
    ScenarioKind,
    Service,
    ServiceId,
    ServiceUnit,
    SpatialUnit,
    UnitId,
)
from tests.fixtures import synthetic


@pytest.mark.parametrize("severity", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_severity_within_bounds_is_accepted(severity: float) -> None:
    assert synthetic.disruption(severity).facility_severities[synthetic.FACILITIES[0]] == severity


@pytest.mark.parametrize("severity", [-0.01, 1.01, float("nan"), float("inf")])
def test_severity_outside_bounds_is_rejected(severity: float) -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        synthetic.disruption(severity)


def test_disruption_requires_rationing_case() -> None:
    with pytest.raises(ValueError, match="rationing"):
        Scenario(ScenarioId("C"), "x", ScenarioKind.DISRUPTION, {})


def test_reference_scenario_flag() -> None:
    scenario = Scenario(
        ScenarioId("C-ref"),
        "minor",
        ScenarioKind.DISRUPTION,
        rationing=Rationing.CONCENTRATED,
        reference_level=ReferenceScenarioLevel.MINOR,
    )
    assert scenario.is_reference
    assert not synthetic.disruption().is_reference


def test_counterfactual_cannot_be_reference() -> None:
    with pytest.raises(ValueError, match="reference"):
        Scenario(
            ScenarioId("C"),
            "x",
            ScenarioKind.COUNTERFACTUAL,
            reference_level=ReferenceScenarioLevel.SEVERE,
        )


def test_entities_are_immutable() -> None:
    unit = synthetic.spatial_unit()
    with pytest.raises(dataclasses.FrozenInstanceError):
        unit.id = UnitId("other")  # type: ignore[misc]
    with pytest.raises(TypeError):
        unit.population_by_group["G-new"] = 1.0  # type: ignore[index]


def test_mapping_inputs_are_copied() -> None:
    source = {synthetic.FACILITIES[0]: 0.5}
    scenario = Scenario(
        ScenarioId("C"), "x", ScenarioKind.DISRUPTION, source, rationing=Rationing.UNIFORM
    )
    source[synthetic.FACILITIES[0]] = 0.9
    assert scenario.facility_severities[synthetic.FACILITIES[0]] == 0.5


def test_negative_population_rejected() -> None:
    with pytest.raises(ValueError, match="population"):
        SpatialUnit(UnitId("U"), population_by_group={synthetic.GROUPS[0]: -1.0})


def test_service_waiting_time_must_be_positive() -> None:
    assert synthetic.service().max_acceptable_wait is None  # value open (OQ-26)
    with pytest.raises(ValueError, match="positive"):
        Service(ServiceId("S"), "x", ServiceUnit.HOUR, max_acceptable_wait=timedelta(0))


def test_facility_capacity_only_for_offered_services() -> None:
    with pytest.raises(ValueError, match="not offered"):
        Facility(
            FacilityId("F"),
            "x",
            "t",
            frozenset({ServiceId("S-1")}),
            capacity={ServiceId("S-2"): CapacityInputs(staff=1.0)},
        )
    with pytest.raises(ValueError, match="staff"):
        CapacityInputs(staff=-1.0)


def test_group_definition_indicators_cannot_be_susceptibility_evidence() -> None:
    group = synthetic.group()
    group.check_susceptibility_indicators(frozenset({"living_alone"}))
    with pytest.raises(ValueError, match="OQ-9"):
        group.check_susceptibility_indicators(frozenset({"age", "living_alone"}))


def test_what_if_interventions_are_typed_placeholders() -> None:
    change = CapacityChange(
        FacilityId("F-1"), ServiceId("S-1"), "staff", CapacityChangeMode.RELATIVE, 20.0
    )
    new = NewFacility(Facility(FacilityId("F-new"), "x", "t", frozenset({ServiceId("S-1")})))
    scenario = Scenario(
        ScenarioId("C-whatif"), "x", ScenarioKind.COUNTERFACTUAL, interventions=[change, new]
    )
    assert scenario.interventions == (change, new)
    assert isinstance(scenario.interventions, tuple)


def test_capacity_change_validates_input_name_and_amount() -> None:
    with pytest.raises(ValueError, match="unknown capacity input"):
        CapacityChange(FacilityId("F"), ServiceId("S"), "beds", CapacityChangeMode.ABSOLUTE, 1)
    with pytest.raises(ValueError, match="finite"):
        CapacityChange(
            FacilityId("F"), ServiceId("S"), "places", CapacityChangeMode.ABSOLUTE, float("nan")
        )

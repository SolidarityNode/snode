"""Synthetic fixtures. Invented values only; no real persons, places or operational data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from solidaritynode_core.model import (
    CapacityInputs,
    Facility,
    FacilityId,
    GroupId,
    PopulationGroup,
    Rationing,
    Scenario,
    ScenarioId,
    ScenarioKind,
    Service,
    ServiceId,
    ServiceUnit,
    SpatialUnit,
    Ticket,
    UnitId,
)

UNITS = (UnitId("U-A"), UnitId("U-B"))
GROUPS = (GroupId("G-older"), GroupId("G-lowinc"))
SERVICES = (ServiceId("S-homecare"), ServiceId("S-clinic"))
FACILITIES = (FacilityId("F-1"), FacilityId("F-2"))
T0 = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)


def spatial_unit() -> SpatialUnit:
    return SpatialUnit(UNITS[0], population_by_group={GROUPS[0]: 120.0, GROUPS[1]: 80.0})


def group() -> PopulationGroup:
    return PopulationGroup(
        GROUPS[0],
        name="Synthetic older group",
        definition_rule="Age >= 65",
        definition_indicators=frozenset({"age"}),
    )


def service() -> Service:
    return Service(SERVICES[0], name="Synthetic home care", unit=ServiceUnit.VISIT)


def facility() -> Facility:
    return Facility(
        FACILITIES[0],
        name="Synthetic facility",
        facility_type="health_centre",
        services=frozenset({SERVICES[0]}),
        capacity={SERVICES[0]: CapacityInputs(staff=3.0, throughput=200.0)},
    )


def disruption(severity: float = 0.5) -> Scenario:
    return Scenario(
        ScenarioId("C-1"),
        name="Synthetic disruption",
        kind=ScenarioKind.DISRUPTION,
        facility_severities={FACILITIES[0]: severity},
        rationing=Rationing.UNIFORM,
    )


def ticket(**overrides: object) -> Ticket:
    fields: dict[str, object] = {
        "unit": UNITS[0],
        "group": GROUPS[0],
        "service": SERVICES[0],
        "facility_id": FACILITIES[0],
        "requested_at": T0,
        "scheduled_at": T0 + timedelta(days=2),
        "fulfilled_at": None,
        "expires_at": T0 + timedelta(days=14),
        "first_request_in_period": True,
    }
    fields.update(overrides)
    return Ticket(**fields)  # type: ignore[arg-type]

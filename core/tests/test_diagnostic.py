"""Known-answer tests of the diagnostic model and scenario overlay on the demo packages (DP-002)."""

from __future__ import annotations

import numpy as np
import pytest

from solidaritynode_core.model import (
    CapacityChange,
    CapacityChangeMode,
    Facility,
    FacilityId,
    NetworkDisruption,
    NewFacility,
    Rationing,
    Scenario,
    ScenarioId,
    ScenarioKind,
    ServiceId,
    TransportMode,
    UnitId,
    get_registry,
)
from solidaritynode_core.scenarios import ScenarioReferenceError, apply_overlay, check_references
from solidaritynode_core.validation import (
    DIAGNOSTIC_LABEL,
    run_diagnostic,
    shortest_travel_times,
)
from tests.fixtures import packages

pytestmark = pytest.mark.skipif(not packages.PACKAGES.exists(), reason="packages not built")

WALK, CAR = TransportMode.WALK, TransportMode.CAR


def _noop(_: float) -> None:
    return None


def close_e02() -> Scenario:
    return Scenario(
        id=ScenarioId("close-e02"),
        name="close E02",
        kind=ScenarioKind.DISRUPTION,
        network_disruption=NetworkDisruption(frozenset({WALK, CAR}), frozenset({"E02"})),
        rationing=Rationing.UNIFORM,
    )


def _cell(result, unit: str, service: str, indicator: str, group: str = "G-OLD"):
    (cell,) = [
        c
        for c in result.cells
        if (c.unit, c.group, c.service, c.indicator) == (unit, group, service, indicator)
    ]
    return cell


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_reproduces_hand_check_travel_times(version: str) -> None:
    area = packages.load(version)
    result = run_diagnostic(area, None, {"n_samples": 10}, 1, _noop)
    check = result.diagnostics["hand_check"]["baseline"]
    assert check["checked"] == 48
    assert check["mismatches"] == []
    assert result.diagnostics["label"] == DIAGNOSTIC_LABEL
    assert result.model_id == "diagnostic-v0"


def test_worked_examples_from_the_demo_readme() -> None:
    area = packages.load("1.0.0")
    walk = shortest_travel_times(area, WALK)
    assert walk[(UnitId("A1"), FacilityId("F3"))] == 6
    assert walk[(UnitId("A1"), FacilityId("F2"))] == 66
    assert shortest_travel_times(area, CAR)[(UnitId("A4"), FacilityId("F2"))] == 15
    closed = shortest_travel_times(area, WALK, frozenset({"E02"}))
    assert closed[(UnitId("A1"), FacilityId("F2"))] == 78


def test_closing_e02_changes_exactly_the_expected_times() -> None:
    area = packages.load("1.0.0")
    expected_changed = {
        (h.mode, h.unit, h.facility)
        for h in area.hand_checks
        if h.closed_edges
        for b in area.hand_checks
        if not b.closed_edges
        and (b.mode, b.unit, b.facility) == (h.mode, h.unit, h.facility)
        and b.travel_time_min != h.travel_time_min
    }
    assert expected_changed  # the demo is built so that some times change
    result = run_diagnostic(area, close_e02(), {"n_samples": 10}, 1, _noop)
    assert result.diagnostics["hand_check"]["scenario"]["checked"] == 48
    assert result.diagnostics["hand_check"]["scenario"]["mismatches"] == []
    changed = {
        (TransportMode(r["mode"]), r["unit_id"], r["facility_id"])
        for r in result.tables["travel_times"]
        if r["before_min"] != r["after_min"]
    }
    assert changed == expected_changed


def test_nearest_facility_time_changes_where_expected() -> None:
    result = run_diagnostic(packages.load("1.0.0"), close_e02(), {"n_samples": 10}, 1, _noop)
    a3 = _cell(result, "A3", "S-HC", "travel_time_walk_min")
    assert (a3.baseline, a3.value, a3.low, a3.high) == (30, 66, 66, 66)
    assert _cell(result, "A3", "S-HC", "closed_edges").value == 1
    assert _cell(result, "A1", "S-HC", "travel_time_walk_min").value == 6  # F3, unaffected
    # 1.1.0: F3 closed (A1 now goes to F1) and F4 added (A3 reaches it across the border).
    rerun = run_diagnostic(packages.load("1.1.0"), close_e02(), {"n_samples": 10}, 1, _noop)
    assert _cell(rerun, "A1", "S-HC", "travel_time_walk_min").value == 30
    assert _cell(rerun, "A3", "S-HC", "travel_time_walk_min").value == 18


def test_results_only_for_core_units_and_every_cell() -> None:
    area = packages.load("1.0.0")
    result = run_diagnostic(area, None, {"n_samples": 5}, 1, _noop)
    assert {c.unit for c in result.cells} == {f"A{i}" for i in range(1, 7)}
    keys = {(c.unit, c.group, c.service, c.indicator) for c in result.cells}
    assert len(keys) == len(result.cells) == 6 * 3 * 2 * 5
    assert len(result.samples) == 6 * 3 * 2


def test_same_seed_same_output_different_seed_differs() -> None:
    area = packages.load("1.0.0")
    a = run_diagnostic(area, close_e02(), {"n_samples": 50}, 7, _noop)
    b = run_diagnostic(area, close_e02(), {"n_samples": 50}, 7, _noop)
    c = run_diagnostic(area, close_e02(), {"n_samples": 50}, 8, _noop)
    assert a.cells == b.cells
    assert all(
        np.array_equal(x.values, y.values) for x, y in zip(a.samples, b.samples, strict=True)
    )
    assert a.cells != c.cells
    noise = _cell(a, "A1", "S-HC", "diagnostic_noise")
    assert noise.low is not None
    assert noise.high is not None
    assert noise.low < noise.high


def test_progress_is_reported_and_can_cancel() -> None:
    seen: list[float] = []
    run_diagnostic(packages.load("1.0.0"), None, {"n_samples": 5}, 1, seen.append)
    assert seen[0] == 0.0
    assert seen[-1] == 1.0
    assert seen == sorted(seen)

    class StopError(Exception):
        pass

    def stop(fraction: float) -> None:
        if fraction > 0.3:
            raise StopError

    with pytest.raises(StopError):
        run_diagnostic(packages.load("1.0.0"), None, {"n_samples": 5}, 1, stop)


def test_overlay_applies_capacity_and_new_facility_and_records_severity() -> None:
    area = packages.load("1.0.0")
    new = Facility(FacilityId("F9"), "New", "desk", frozenset({ServiceId("S-SD")}))
    scenario = Scenario(
        id=ScenarioId("c"),
        name="c",
        kind=ScenarioKind.DISRUPTION,
        facility_severities={FacilityId("F1"): 0.5},
        interventions=(
            CapacityChange(
                FacilityId("F1"), ServiceId("S-HC"), "staff", CapacityChangeMode.RELATIVE, 25
            ),
            NewFacility(new, node_id="N-A4"),
        ),
        rationing=Rationing.UNIFORM,
    )
    overlay = apply_overlay(area, scenario)
    f1 = next(f for f in overlay.area.facilities if f.id == "F1")
    assert f1.capacity[ServiceId("S-HC")].staff == 5
    assert overlay.area.facility_units[FacilityId("F9")] == "A4"
    assert {c.kind for c in overlay.changes} == {"capacity", "new", "severity"}
    # Severity is recorded, never applied to capacity (Paper 3 method).
    assert f1.capacity[ServiceId("S-SD")].throughput == 120
    result = run_diagnostic(area, scenario, {"n_samples": 5}, 1, _noop)
    assert _cell(result, "A4", "S-SD", "facilities_affected").value == 1
    assert _cell(result, "A4", "S-SD", "travel_time_car_min").value == 0
    assert _cell(result, "A2", "S-HC", "facilities_affected").value == 1


def test_references_to_missing_or_closed_features_are_reported() -> None:
    scenario = Scenario(
        id=ScenarioId("c"),
        name="c",
        kind=ScenarioKind.DISRUPTION,
        facility_severities={FacilityId("F4"): 1.0, FacilityId("F3"): 0.5},
        network_disruption=NetworkDisruption(frozenset({WALK}), frozenset({"E01", "E99"})),
        rationing=Rationing.CONCENTRATED,
    )
    assert check_references(packages.load("1.0.0"), scenario) == [
        "facility F4: closed or missing in data 1.0.0",
        "edge E01: cannot be closed (closable = false)",
        "edge E99: closed or missing in data 1.0.0",
    ]
    problems = check_references(packages.load("1.1.0"), scenario)
    assert "facility F3: closed or missing in data 1.1.0" in problems
    with pytest.raises(ScenarioReferenceError):
        apply_overlay(packages.load("1.1.0"), scenario)


def test_registry_holds_only_the_diagnostic_model() -> None:
    registry = get_registry()
    assert registry.ids() == ("diagnostic-v0",)
    spec = registry.get("diagnostic-v0")
    assert spec.diagnostic is True
    assert spec.version == "0.1.0"
    with pytest.raises(KeyError):
        registry.get("vulnerability")

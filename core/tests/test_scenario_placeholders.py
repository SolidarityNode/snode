"""Network and population intervention placeholders and the order of application (ADR 0016)."""

from __future__ import annotations

import pytest

from solidaritynode_core.model import (
    ChangeMode,
    EdgeChange,
    EdgeQuantity,
    GroupId,
    NetworkDisruption,
    NewEdge,
    PopulationChange,
    Rationing,
    Scenario,
    ScenarioId,
    ScenarioKind,
    TransportMode,
    UnitId,
)
from solidaritynode_core.scenarios import apply_overlay, check_references
from solidaritynode_core.validation import run_diagnostic, shortest_travel_times
from tests.fixtures import packages

pytestmark = pytest.mark.skipif(not packages.PACKAGES.exists(), reason="packages not built")
WALK = TransportMode.WALK


def _scenario(*interventions: object, close: frozenset[str] = frozenset()) -> Scenario:
    return Scenario(
        id=ScenarioId("placeholders"),
        name="placeholders",
        kind=ScenarioKind.DISRUPTION if close else ScenarioKind.COUNTERFACTUAL,
        interventions=tuple(interventions),  # type: ignore[arg-type]
        network_disruption=NetworkDisruption(frozenset({WALK}), close) if close else None,
        rationing=Rationing.UNIFORM if close else None,
    )


EDGE = EdgeChange("E01", WALK, EdgeQuantity.TRAVEL_TIME, ChangeMode.RELATIVE, -20)
NEW_EDGE = NewEdge("E-NEW", "N-A1", "N-A5", {WALK: 10.0})
POPULATION = PopulationChange(UnitId("A1"), GroupId("G-OLD"), ChangeMode.ABSOLUTE, 10)


def test_placeholders_are_checked_recorded_in_order_and_not_applied() -> None:
    area = packages.load("1.0.0")
    # Disruptions come after interventions, so the new edge of the scenario can be closed.
    scenario = _scenario(POPULATION, NEW_EDGE, EDGE, close=frozenset({"E-NEW"}))
    assert check_references(area, scenario) == []
    overlay = apply_overlay(area, scenario)
    assert overlay.recorded == (
        "edge E01 walk travel_time -20 % (recorded only)",
        "new edge E-NEW N-A1-N-A5 (walk 10 min) (recorded only)",
        "unit A1 group G-OLD population +10 persons (recorded only)",
    )
    assert overlay.area == area  # no behaviour: the network and population are unchanged
    assert overlay.closed_edges == frozenset({"E-NEW"})
    result = run_diagnostic(area, scenario, {"n_samples": 5}, 1, lambda _: None)
    assert result.diagnostics["recorded_only"] == list(overlay.recorded)
    baseline = shortest_travel_times(area, WALK)
    after = {
        (r["unit_id"], r["facility_id"]): r["after_min"]
        for r in result.tables["travel_times"]
        if r["mode"] == "walk"
    }
    assert all(after[key] == minutes for key, minutes in baseline.items())


def test_scenarios_without_placeholders_keep_their_diagnostics() -> None:
    result = run_diagnostic(packages.load("1.0.0"), None, {"n_samples": 5}, 1, lambda _: None)
    assert "recorded_only" not in result.diagnostics


@pytest.mark.parametrize(
    ("intervention", "problem"),
    [
        (EdgeChange("E99", WALK, EdgeQuantity.SPEED, ChangeMode.RELATIVE, 10), "edge E99: closed"),
        (
            EdgeChange(
                "E01", TransportMode.PUBLIC_TRANSPORT, EdgeQuantity.SPEED, ChangeMode.RELATIVE, 5
            ),
            "has no public_transport travel time",
        ),
        (
            EdgeChange("E01", WALK, EdgeQuantity.TRAVEL_TIME, ChangeMode.ABSOLUTE, -999),
            "travel time would become negative",
        ),
        (NewEdge("E01", "N-A1", "N-A5", {WALK: 1.0}), "new edge E01: id already exists"),
        (NewEdge("E-NEW", "N-A1", "N-ZZ", {WALK: 1.0}), "network node N-ZZ missing"),
        (PopulationChange(UnitId("Z9"), GroupId("G-OLD"), ChangeMode.ABSOLUTE, 1), "unit Z9"),
        (PopulationChange(UnitId("A1"), GroupId("G-ZZ"), ChangeMode.ABSOLUTE, 1), "group G-ZZ"),
        (
            PopulationChange(UnitId("A1"), GroupId("G-OLD"), ChangeMode.ABSOLUTE, -1_000_000),
            "population would become negative",
        ),
    ],
)
def test_placeholder_references_are_checked(intervention: object, problem: str) -> None:
    problems = check_references(packages.load("1.0.0"), _scenario(intervention))
    assert any(problem in p for p in problems), problems


def test_a_new_edge_marked_not_closable_cannot_be_closed() -> None:
    edge = NewEdge("E-NEW", "N-A1", "N-A5", {WALK: 10.0}, closable=False)
    problems = check_references(packages.load("1.0.0"), _scenario(edge, close=frozenset({"E-NEW"})))
    assert problems == ["edge E-NEW: cannot be closed (closable = false)"]


def test_placeholder_values_are_validated() -> None:
    with pytest.raises(ValueError, match="above -100"):
        EdgeChange("E01", WALK, EdgeQuantity.SPEED, ChangeMode.RELATIVE, -100)
    with pytest.raises(ValueError, match="must differ"):
        NewEdge("E-NEW", "N-A1", "N-A1", {WALK: 1.0})
    with pytest.raises(ValueError, match="at least one mode"):
        NewEdge("E-NEW", "N-A1", "N-A5", {})
    with pytest.raises(ValueError, match="finite"):
        PopulationChange(UnitId("A1"), GroupId("G-OLD"), ChangeMode.ABSOLUTE, float("nan"))

"""Diagnostic model ``diagnostic-v0`` that proves the run pipeline; not a research result.

Papers 1–4 are not implemented yet. This model exists only so the platform (scenarios, runs,
background jobs, result storage, maps, comparison, export) can be tested end to end on the
synthetic demo data. Its outputs are labelled ``diagnostic`` everywhere and must never be read
as accessibility, need, vulnerability or resilience. It does three things:

1. **Overlay report** (Spec 00 §3 Scenario): applies the scenario overlay
   (:func:`~solidaritynode_core.scenarios.apply_overlay`) and reports per spatial unit what
   changed: facilities affected, capacity-input changes, closed edges. Severities are recorded,
   not applied.
2. **Shortest-path travel times** on the package network, before and after the scenario, from
   every unit centroid to every open facility, per mode, checked against the package's
   hand-check table (DP-002). This is a plain shortest path on the given edge times: no access
   weight (OQ-3), no mode combination (OQ-5), no group-specific speeds (OQ-6); it is not the
   Paper 1 §5 accessibility model.
3. **Seeded noise** ``diagnostic_noise``: standard normal draws per ``unit × group × service``
   from ``numpy.random.default_rng(seed)``, so uncertainty display and reproducibility (same seed,
   same output) can be tested. It means nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import networkx as nx
import numpy as np

from solidaritynode_core.model.entities import Scenario, ScenarioKind, TransportMode
from solidaritynode_core.model.ids import FacilityId, GroupId, ScenarioId, ServiceId, UnitId
from solidaritynode_core.model.registry import (
    STATIC_TIME,
    CellSamples,
    IndicatorSpec,
    ModelResult,
    ModelSpec,
    ProgressFn,
    ResultCell,
)
from solidaritynode_core.model.study_area import StudyArea
from solidaritynode_core.scenarios.overlay import apply_overlay

__all__ = [
    "DIAGNOSTIC_LABEL",
    "DIAGNOSTIC_MODEL_ID",
    "DIAGNOSTIC_MODEL_VERSION",
    "DIAGNOSTIC_V0",
    "EMPTY_SCENARIO",
    "run_diagnostic",
    "shortest_travel_times",
]

DIAGNOSTIC_MODEL_ID = "diagnostic-v0"
DIAGNOSTIC_MODEL_VERSION = "0.1.0"
DIAGNOSTIC_LABEL = "Diagnostic model: not a research result"
MODES: tuple[TransportMode, ...] = (TransportMode.WALK, TransportMode.CAR)
_TOLERANCE = 1e-6
_MAX_SAMPLES = 10_000

EMPTY_SCENARIO = Scenario(
    id=ScenarioId("baseline"), name="Baseline (no changes)", kind=ScenarioKind.COUNTERFACTUAL
)
"""The empty overlay: running it gives the baseline."""

INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec("diagnostic_noise", "Diagnostic noise (meaningless)", "1", False, True),
    *(
        IndicatorSpec(
            f"travel_time_{m.value}_min",
            f"Shortest {m.value} time to nearest facility offering the service (diagnostic)",
            "min",
            True,
            False,
        )
        for m in MODES
    ),
    IndicatorSpec(
        "facilities_affected",
        "Facilities in the unit changed by the scenario, for this service",
        "count",
        True,
        False,
    ),
    IndicatorSpec("closed_edges", "Closed network edges touching the unit", "count", True, False),
)


def shortest_travel_times(
    area: StudyArea, mode: TransportMode, closed_edges: frozenset[str] = frozenset()
) -> dict[tuple[UnitId, FacilityId], float]:
    """Return shortest network times from every unit centroid to every facility (diagnostic).

    Plain Dijkstra on the edge times of ``mode``, with ``closed_edges`` removed. Not the
    Paper 1 §5 travel time model (OQ-3, OQ-5 open).

    Args:
        area: Study area (core and buffer units, open facilities, network).
        mode: Transport mode whose edge times are used.
        closed_edges: Edge ids to leave out.

    Returns:
        Minutes per ``(unit, facility)``; unreachable pairs are absent.
    """
    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(area.node_units)
    for edge in area.edges:
        minutes = edge.travel_time_min.get(mode)
        if edge.id in closed_edges or minutes is None:
            continue
        if graph.has_edge(edge.from_node, edge.to_node):
            minutes = min(minutes, graph.edges[edge.from_node, edge.to_node]["weight"])
        graph.add_edge(edge.from_node, edge.to_node, weight=minutes)
    times: dict[tuple[UnitId, FacilityId], float] = {}
    for unit in area.units:
        source = area.unit_nodes[unit.id]
        if source not in graph:
            continue
        reached = nx.single_source_dijkstra_path_length(graph, source, weight="weight")
        for facility in area.facilities:
            node = area.facility_nodes[facility.id]
            if node in reached:
                times[(unit.id, facility.id)] = float(reached[node])
    return times


def _check(
    expected: Mapping[tuple[str, str, str], float],
    computed: Mapping[TransportMode, Mapping[tuple[UnitId, FacilityId], float]],
) -> dict[str, Any]:
    mismatches = []
    for (mode, unit, facility), minutes in sorted(expected.items()):
        got = computed[TransportMode(mode)].get((UnitId(unit), FacilityId(facility)))
        if got is None or abs(got - minutes) > _TOLERANCE:
            mismatches.append(
                {"mode": mode, "unit": unit, "facility": facility, "expected": minutes, "got": got}
            )
    return {
        "available": bool(expected),
        "checked": len(expected),
        "passed": len(expected) - len(mismatches),
        "mismatches": mismatches,
    }


def _nearest(
    times: Mapping[tuple[UnitId, FacilityId], float],
    unit: UnitId,
    facilities: list[FacilityId],
) -> float | None:
    values = [times[(unit, f)] for f in facilities if (unit, f) in times]
    return min(values) if values else None


def run_diagnostic(
    area: StudyArea,
    scenario: Scenario | None,
    config: Mapping[str, Any],
    seed: int,
    progress: ProgressFn,
) -> ModelResult:
    """Run ``diagnostic-v0`` (see the module docstring); not a research result.

    Args:
        area: Study area of one data package version.
        scenario: Overlay to apply; ``None`` runs the baseline.
        config: ``n_samples`` (int, 1–10000, default 200) draws of ``diagnostic_noise``.
        seed: Seed of ``numpy.random.default_rng``; same seed, same output.
        progress: Called with the completed fraction; may raise to cancel.

    Returns:
        Cells for core units only (OQ-28): ``diagnostic_noise`` (5th–95th percentile interval),
        nearest-facility travel time per mode before (``baseline``) and after the scenario,
        ``facilities_affected`` and ``closed_edges``. Tables ``travel_times`` and
        ``unit_changes``; diagnostics with the hand-check result and :data:`DIAGNOSTIC_LABEL`.
    """
    n_samples = int(config.get("n_samples", 200))
    if not 1 <= n_samples <= _MAX_SAMPLES:
        raise ValueError(f"n_samples must be in [1, {_MAX_SAMPLES}]")
    scenario = scenario or EMPTY_SCENARIO
    progress(0.0)
    overlay = apply_overlay(area, scenario)
    after_area = overlay.area
    progress(0.1)

    before: dict[TransportMode, dict[tuple[UnitId, FacilityId], float]] = {}
    after: dict[TransportMode, dict[tuple[UnitId, FacilityId], float]] = {}
    closed_by_mode: dict[TransportMode, frozenset[str]] = {}
    for k, mode in enumerate(MODES):
        closed = overlay.closed_edges if mode in overlay.closed_modes else frozenset()
        closed_by_mode[mode] = closed
        before[mode] = shortest_travel_times(area, mode)
        after[mode] = shortest_travel_times(after_area, mode, closed)
        progress(0.1 + 0.4 * (k + 1) / len(MODES))

    expected_before: dict[tuple[str, str, str], float] = {}
    expected_after: dict[tuple[str, str, str], float] = {}
    for check in area.hand_checks:
        key = (check.mode.value, check.unit, check.facility)
        if not check.closed_edges:
            expected_before[key] = check.travel_time_min
        if check.closed_edges == closed_by_mode[check.mode]:
            expected_after[key] = check.travel_time_min
    diagnostics: dict[str, Any] = {
        "label": DIAGNOSTIC_LABEL,
        "hand_check": {
            "baseline": _check(expected_before, before),
            "scenario": _check(expected_after, after),
        },
        "closed_edges": sorted(overlay.closed_edges),
        "closed_modes": sorted(m.value for m in overlay.closed_modes),
    }
    progress(0.6)

    travel_rows: list[dict[str, Any]] = []
    for mode in MODES:
        for unit in area.units:
            for facility in after_area.facilities:
                pair = (unit.id, facility.id)
                check_key = (mode.value, unit.id, facility.id)
                travel_rows.append(
                    {
                        "unit_id": unit.id,
                        "facility_id": facility.id,
                        "mode": mode.value,
                        "before_min": before[mode].get(pair),
                        "after_min": after[mode].get(pair),
                        "expected_before_min": expected_before.get(check_key),
                        "expected_after_min": expected_after.get(check_key),
                    }
                )

    edges = {e.id: e for e in area.edges}
    closed_touching: dict[UnitId, list[str]] = {}
    for eid in sorted(overlay.closed_edges):
        edge = edges[eid]
        for unit_id in {area.node_units[edge.from_node], area.node_units[edge.to_node]}:
            closed_touching.setdefault(unit_id, []).append(eid)
    unit_rows = []
    for unit in area.units:
        changes = [c for c in overlay.changes if c.unit == unit.id]
        unit_rows.append(
            {
                "unit_id": unit.id,
                "role": area.unit_roles[unit.id],
                "facilities_affected": len({c.facility for c in changes}),
                "capacity_changes": sum(1 for c in changes if c.kind == "capacity"),
                "closed_edges": len(closed_touching.get(unit.id, [])),
                "details": [f"{c.facility}: {c.detail}" for c in changes]
                + [f"edge {e} closed" for e in closed_touching.get(unit.id, [])],
            }
        )
    progress(0.7)

    rng = np.random.default_rng(seed)
    cells: list[ResultCell] = []
    samples: list[CellSamples] = []
    offering_before = {
        s.id: [f.id for f in area.facilities if s.id in f.services] for s in area.services
    }
    offering_after = {
        s.id: [f.id for f in after_area.facilities if s.id in f.services] for s in area.services
    }
    units = sorted(area.core_units, key=lambda u: u.id)
    groups = sorted(area.groups, key=lambda g: g.id)
    services = sorted(area.services, key=lambda s: s.id)
    for unit in units:
        for group in groups:
            for service in services:
                cells.extend(
                    _cells(
                        unit.id,
                        group.id,
                        service.id,
                        before,
                        after,
                        offering_before[service.id],
                        offering_after[service.id],
                        len(
                            {
                                c.facility
                                for c in overlay.changes
                                if c.unit == unit.id and service.id in c.services
                            }
                        ),
                        len(closed_touching.get(unit.id, [])),
                    )
                )
                draws = rng.standard_normal(n_samples)
                samples.append(
                    CellSamples(
                        unit.id, group.id, service.id, STATIC_TIME, "diagnostic_noise", draws
                    )
                )
                low, high = np.quantile(draws, [0.05, 0.95])
                cells.append(
                    ResultCell(
                        unit.id,
                        group.id,
                        service.id,
                        STATIC_TIME,
                        "diagnostic_noise",
                        float(draws.mean()),
                        float(low),
                        float(high),
                    )
                )
    progress(1.0)
    return ModelResult(
        model_id=DIAGNOSTIC_MODEL_ID,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        indicators=INDICATORS,
        cells=tuple(cells),
        samples=tuple(samples),
        tables={"travel_times": tuple(travel_rows), "unit_changes": tuple(unit_rows)},
        diagnostics=diagnostics,
    )


def _cells(
    unit: UnitId,
    group: GroupId,
    service: ServiceId,
    before: Mapping[TransportMode, Mapping[tuple[UnitId, FacilityId], float]],
    after: Mapping[TransportMode, Mapping[tuple[UnitId, FacilityId], float]],
    offering_before: list[FacilityId],
    offering_after: list[FacilityId],
    facilities_affected: int,
    closed_edges: int,
) -> list[ResultCell]:
    out = []
    for mode in MODES:
        value = _nearest(after[mode], unit, offering_after)
        base = _nearest(before[mode], unit, offering_before)
        out.append(
            ResultCell(
                unit,
                group,
                service,
                STATIC_TIME,
                f"travel_time_{mode.value}_min",
                value,
                value,
                value,
                base,
            )
        )
    for indicator, count in (
        ("facilities_affected", facilities_affected),
        ("closed_edges", closed_edges),
    ):
        value = float(count)
        out.append(ResultCell(unit, group, service, STATIC_TIME, indicator, value, value, value))
    return out


def _run(
    area: StudyArea,
    scenario: object,
    config: Mapping[str, Any],
    seed: int,
    progress: ProgressFn,
) -> ModelResult:
    if scenario is not None and not isinstance(scenario, Scenario):
        raise TypeError("diagnostic-v0 expects a core Scenario or None")
    return run_diagnostic(area, scenario, config, seed, progress)


DIAGNOSTIC_V0 = ModelSpec(
    id=DIAGNOSTIC_MODEL_ID,
    version=DIAGNOSTIC_MODEL_VERSION,
    description=DIAGNOSTIC_LABEL,
    diagnostic=True,
    default_config={"n_samples": 200},
    run=_run,
)
"""Registry entry of the diagnostic model."""

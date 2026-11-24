"""The synthetic demo dataset is complete, consistent and fits the core model.

Checks the structure required for tests and UAT (two municipalities, 6 + 2 units, 3 groups,
2 services, 4 facilities with one across the border, a walking and car network with a badly
connected unit and a closable edge, the hand-check table and the reference scenario). The
shortest-path search below is test code that re-derives the hand-check table from the edge
list; it is not a method of ``core``.
"""

from __future__ import annotations

import hashlib
import heapq
import re
from collections import Counter
from datetime import timedelta

import pytest

from solidaritynode_core.model import (
    FacilityId,
    NetworkDisruption,
    Rationing,
    Scenario,
    ScenarioId,
    ScenarioKind,
    Service,
    ServiceId,
    ServiceUnit,
    TransportMode,
)
from tests.fixtures import demo

pytestmark = pytest.mark.skipif(not demo.DEMO_DIR.exists(), reason="demo dataset not present")


def test_manifest_checksums_match_files() -> None:
    manifest = demo.read_json("manifest.json")
    assert manifest["synthetic"] is True
    assert manifest["processing_notes"] == ["DP-001"]
    listed = {f["path"] for f in manifest["files"]}
    on_disk = {
        p.relative_to(demo.DEMO_DIR).as_posix()
        for p in demo.DEMO_DIR.rglob("*")
        if p.is_file() and p.name not in {"manifest.json", "README.md"}
    }
    assert listed == on_disk
    for entry in manifest["files"]:
        data = (demo.DEMO_DIR / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]


def test_study_area_has_core_and_buffer_municipalities() -> None:
    assert demo.gpkg_srs_ids() == {2100}
    municipalities = {m["municipality_id"]: m["role"] for m in demo.read_layer("municipalities")}
    assert municipalities == {"M-A": "core", "M-B": "buffer"}
    units = demo.read_layer("spatial_units")
    assert Counter((u["municipality_id"], u["role"]) for u in units) == {
        ("M-A", "core"): 6,
        ("M-B", "buffer"): 2,
    }
    centroids = demo.read_layer("unit_centroids")
    assert {c["unit_id"] for c in centroids} == {u["unit_id"] for u in units}


def test_population_by_three_groups_for_every_unit() -> None:
    groups = {g["group_id"] for g in demo.read_csv("groups.csv")}
    assert len(groups) == 3
    units = {u["unit_id"] for u in demo.read_layer("spatial_units")}
    rows = demo.read_csv("population.csv")
    assert {(r["unit_id"], r["group_id"]) for r in rows} == {(u, g) for u in units for g in groups}
    assert all(int(r["population"]) >= 0 for r in rows)


def _iso_days(value: str) -> timedelta:
    match = re.fullmatch(r"P(\d+)D", value)
    assert match, value
    return timedelta(days=int(match.group(1)))


def test_services_fit_the_core_model() -> None:
    rows = demo.read_csv("services.csv")
    assert len(rows) == 2
    services = [
        Service(
            ServiceId(r["service_id"]),
            r["name"],
            ServiceUnit(r["service_unit"]),
            max_acceptable_wait=_iso_days(r["max_acceptable_wait"]),
        )
        for r in rows
    ]
    assert len({s.unit for s in services}) == 2


def test_four_facilities_one_across_the_border() -> None:
    facilities = demo.read_layer("facilities")
    assert len(facilities) == 4
    assert [f["facility_id"] for f in facilities if f["role"] == "buffer"] == ["F4"]
    offered = demo.read_csv("facility_services.csv")
    assert {r["facility_id"] for r in offered} == {f["facility_id"] for f in facilities}
    services = {s["service_id"] for s in demo.read_csv("services.csv")}
    assert {r["service_id"] for r in offered} <= services


def _edges(mode: str) -> list[dict[str, str]]:
    return [e for e in demo.read_csv("network_edges.csv") if e["mode"] == mode]


def test_network_has_walk_and_car_a_closable_edge_and_a_badly_connected_unit() -> None:
    modes = {e["mode"] for e in demo.read_csv("network_edges.csv")}
    assert modes == {TransportMode.WALK.value, TransportMode.CAR.value}
    nodes = {n["node_id"] for n in demo.read_csv("network_nodes.csv")}
    for mode in modes:
        edges = _edges(mode)
        assert {e["from_node_id"] for e in edges} | {e["to_node_id"] for e in edges} <= nodes
        assert [e["edge_id"] for e in edges if e["closable"] == "true"] == ["E02"]
        degree = Counter([e["from_node_id"] for e in edges] + [e["to_node_id"] for e in edges])
        assert degree["N-A4"] == 1


def _shortest(mode: str, source: str, closed: set[str]) -> dict[str, float]:
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for e in _edges(mode):
        if e["edge_id"] in closed:
            continue
        minutes = float(e["travel_time_min"])
        adjacency.setdefault(e["from_node_id"], []).append((e["to_node_id"], minutes))
        adjacency.setdefault(e["to_node_id"], []).append((e["from_node_id"], minutes))
    best: dict[str, float] = {}
    heap = [(0.0, source)]
    while heap:
        dist, node = heapq.heappop(heap)
        if node in best:
            continue
        best[node] = dist
        for nxt, minutes in adjacency.get(node, []):
            heapq.heappush(heap, (dist + minutes, nxt))
    return best


def test_hand_check_table_matches_the_network() -> None:
    scenario = demo.read_json("scenarios/C-DEMO-REF.json")
    closed_by = {
        "baseline": set(),
        scenario["id"]: set(scenario["network_disruption"]["affected_link_ids"]),
    }
    node_of_facility = {f["facility_id"]: f["node_id"] for f in demo.read_layer("facilities")}
    rows = demo.read_csv("hand_check_travel_times.csv")
    assert len(rows) == 2 * 2 * 8 * 4
    for r in rows:
        times = _shortest(r["mode"], f"N-{r['unit_id']}", closed_by[r["scenario_id"]])
        assert times[node_of_facility[r["facility_id"]]] == pytest.approx(
            float(r["travel_time_min"])
        ), r


def test_closing_the_edge_lengthens_some_trips() -> None:
    rows = demo.read_csv("hand_check_travel_times.csv")
    key = lambda r: (r["mode"], r["unit_id"], r["facility_id"])  # noqa: E731
    base = {key(r): float(r["travel_time_min"]) for r in rows if r["scenario_id"] == "baseline"}
    ref = {key(r): float(r["travel_time_min"]) for r in rows if r["scenario_id"] != "baseline"}
    assert all(ref[k] >= base[k] for k in base)
    assert any(ref[k] > base[k] for k in base)


def test_reference_scenario_fits_the_core_model() -> None:
    raw = demo.read_json("scenarios/C-DEMO-REF.json")
    scenario = Scenario(
        ScenarioId(raw["id"]),
        raw["name"],
        ScenarioKind(raw["kind"]),
        {FacilityId(k): v for k, v in raw["facility_severities"].items()},
        network_disruption=NetworkDisruption(
            frozenset(TransportMode(m) for m in raw["network_disruption"]["modes"]),
            frozenset(raw["network_disruption"]["affected_link_ids"]),
        ),
        rationing=Rationing(raw["rationing"]),
    )
    assert dict(scenario.facility_severities) == {FacilityId("F1"): 0.5}
    assert scenario.network_disruption is not None
    assert scenario.network_disruption.affected_link_ids == {"E02"}
    assert not scenario.is_reference

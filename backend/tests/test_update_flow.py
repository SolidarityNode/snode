"""Package update flow (task: import 1.0.0, run, import 1.1.0, revalidate, rerun, compare)."""

from __future__ import annotations

from tests.conftest import CLOSE_E02, import_version

WITH_F3 = {
    "name": "F3 staff +1 and close E02",
    "visibility": "shared",
    "body": {
        **CLOSE_E02["body"],
        "capacity_changes": [
            {
                "facility_id": "F3",
                "service_id": "S-HC",
                "capacity_input": "staff",
                "mode": "absolute",
                "amount": 1,
            }
        ],
    },
}


def _walk(client, run_id: str, unit: str) -> dict:  # type: ignore[no-untyped-def,type-arg]
    rows = client.get(
        f"/runs/{run_id}/results",
        params={"group": "G-OLD", "service": "S-HC", "indicator": "travel_time_walk_min"},
    ).json()
    return next(r for r in rows if r["unit_id"] == unit)


def test_package_update_flow(as_admin, as_analyst, worker) -> None:  # type: ignore[no-untyped-def]
    # 1.0.0, a scenario and its run.
    import_version(as_admin, "1.0.0")
    worker.run_until_idle()
    close = as_analyst.post("/scenarios", json=CLOSE_E02).json()
    with_f3 = as_analyst.post("/scenarios", json=WITH_F3).json()
    old_run = as_analyst.post("/runs", json={"scenario_id": close["id"]}).json()
    worker.run_until_idle()
    before = _walk(as_analyst, old_run["id"], "A3")
    assert (before["value"], before["edge_effect_warning"]) == (66, True)
    assert _walk(as_analyst, old_run["id"], "A6")["edge_effect_warning"] is True

    # Preview lists exactly the expected changes; import 1.1.0.
    preview = as_admin.post("/packages/preview", json={"name": "demo-1.1.0"}).json()
    facilities = preview["layers"]["facilities"]
    assert (facilities["added"], facilities["closed"]) == (["F4"], ["F3"])
    assert [c["id"] for c in facilities["changed"]] == ["F2"]
    outcome = import_version(as_admin, "1.1.0")

    # The scenario that refers to the closed F3 is reported, not silently dropped.
    assert outcome["revalidation"] == [
        {
            "scenario_id": with_f3["id"],
            "name": WITH_F3["name"],
            "problems": ["facility F3: closed or missing in the data version"],
        }
    ]
    listed = {s["id"]: s for s in as_analyst.get("/scenarios").json()}
    assert listed[with_f3["id"]]["problems"]
    assert listed[close["id"]]["problems"] == []
    refused = as_analyst.post("/runs", json={"scenario_id": with_f3["id"]})
    assert refused.status_code == 422
    assert refused.json()["detail"]["problems"]

    # The old run still points to 1.0.0 and still reproduces.
    assert as_analyst.get(f"/runs/{old_run['id']}").json()["package_version"] == "1.0.0"
    repro = as_analyst.post(
        "/runs",
        json={
            "scenario_id": close["id"],
            "data_version_id": old_run["data_version_id"],
            "force": True,
        },
    ).json()
    assert repro["package_version"] == "1.0.0"
    assert repro["input_hash"] == old_run["input_hash"]

    # Rerun on 1.1.0: differs where expected, and the edge-effect warning is gone.
    new_run = as_analyst.post("/runs", json={"scenario_id": close["id"]}).json()
    assert new_run["package_version"] == "1.1.0"
    worker.run_until_idle()
    old_rows = as_analyst.get(f"/runs/{old_run['id']}/results").json()
    assert as_analyst.get(f"/runs/{repro['id']}/results").json() == old_rows
    after = _walk(as_analyst, new_run["id"], "A3")
    assert (after["value"], after["edge_effect_warning"]) == (18, False)  # F4 across the border
    assert _walk(as_analyst, new_run["id"], "A1")["value"] == 30  # F3 closed: A1 goes to F1
    assert _walk(as_analyst, new_run["id"], "A6")["edge_effect_warning"] is False
    assert as_analyst.get(f"/runs/{new_run['id']}").json()["edge_effect_units"] == []

    # Comparison across data versions only between runs of the same scenario, labelled.
    cross = as_analyst.get(f"/runs/{new_run['id']}/compare", params={"with": old_run["id"]}).json()
    assert cross["cross_data_version"] is True
    assert "across data versions 1.0.0 → 1.1.0" in cross["label"]

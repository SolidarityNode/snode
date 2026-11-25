"""Run lifecycle, cached reruns, cancel, worker restart, comparison and export (ADR 0006, 0017)."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
from sqlalchemy import text

from solidaritynode_backend.worker import Worker, build_worker
from tests.conftest import CLOSE_E02, import_version


def _ready(as_admin, worker) -> int:  # type: ignore[no-untyped-def]
    dv = import_version(as_admin, "1.0.0")["data_version_id"]
    assert worker.run_until_idle() == 1  # the baseline run queued by the import
    return int(dv)


def test_run_lifecycle_and_results(as_admin, as_analyst, worker, settings) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    created = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 7})
    assert created.status_code == 201
    run = created.json()
    assert (run["status"], run["progress"]) == ("queued", 0)
    for key in (
        "scenario_version",
        "package_id",
        "package_version",
        "code_version",
        "model_id",
        "model_version",
        "seed",
        "config",
        "input_hash",
    ):
        assert run[key] not in (None, ""), key
    assert run["model_id"] == "diagnostic-v0"
    assert run["diagnostic"] is True
    assert run["code_version"] == "test-commit"
    assert run["edge_effect_units"] == ["A3", "A6"]
    assert as_analyst.get(f"/runs/{run['id']}/results").status_code == 409
    assert worker.run_until_idle() == 1
    done = as_analyst.get(f"/runs/{run['id']}").json()
    assert (done["status"], done["progress"]) == ("succeeded", 100)
    assert done["diagnostics"]["hand_check"]["baseline"]["mismatches"] == []
    assert done["diagnostics"]["hand_check"]["scenario"]["checked"] == 48
    rows = as_analyst.get(
        f"/runs/{run['id']}/results",
        params={"group": "G-OLD", "service": "S-HC", "indicator": "travel_time_walk_min"},
    ).json()
    a3 = next(r for r in rows if r["unit_id"] == "A3")
    assert (a3["baseline"], a3["median"], a3["edge_effect_warning"]) == (30, 66, True)
    assert {r["unit_id"] for r in rows} == {"A1", "A2", "A3", "A4", "A5", "A6"}  # core only
    samples = pq.read_table(Path(settings.results_dir) / "runs" / run["id"] / "samples.parquet")
    assert samples.num_rows == 6 * 3 * 2 * 200
    travel = as_analyst.get(f"/runs/{run['id']}/tables/travel_times").json()
    assert any(r["before_min"] != r["after_min"] for r in travel)


def test_cached_rerun_and_forced_rerun(as_admin, as_analyst, worker) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    first = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    worker.run_until_idle()
    again = as_analyst.post("/runs", json={"scenario_id": sid})
    assert again.status_code == 200
    assert again.json()["reused"] is True
    assert again.json()["id"] == first["id"]
    forced = as_analyst.post("/runs", json={"scenario_id": sid, "force": True})
    assert forced.status_code == 201
    assert forced.json()["id"] != first["id"]
    assert forced.json()["input_hash"] == first["input_hash"]
    other_seed = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 2}).json()
    assert other_seed["input_hash"] != first["input_hash"]
    worker.run_until_idle()
    a = as_analyst.get(f"/runs/{first['id']}/results").json()
    b = as_analyst.get(f"/runs/{forced.json()['id']}/results").json()
    assert a == b  # same inputs, same seed: identical results (reproducible)


def test_cancel_queued_and_running(as_admin, as_analyst, worker) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    queued = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    cancelled = as_analyst.post(f"/runs/{queued['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert worker.run_until_idle() == 0
    running = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 3}).json()
    claimed = worker.claim()
    assert claimed is not None
    flagged = as_analyst.post(f"/runs/{running['id']}/cancel").json()
    assert flagged["status"] == "running"
    worker.execute(*claimed)
    final = as_analyst.get(f"/runs/{running['id']}").json()
    assert final["status"] == "cancelled"
    assert "Cancelled" in final["error"]
    assert as_analyst.get(f"/runs/{running['id']}/results").status_code == 409


def test_worker_restart_fails_interrupted_runs(
    as_admin, as_analyst, worker, engine, settings
) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    run = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    assert worker.claim() is not None  # the worker "dies" here, leaving the job running
    restarted: Worker = build_worker(settings, engine)
    assert restarted.fail_stale() == 0  # its lease has not expired yet
    with engine.begin() as conn:  # ... and now it has (no heartbeat for 10 minutes)
        conn.execute(text("UPDATE jobs SET heartbeat_at = now() - interval '10 minutes'"))
    assert restarted.fail_stale() == 1
    failed = as_analyst.get(f"/runs/{run['id']}").json()
    assert failed["status"] == "failed"
    assert "Interrupted" in failed["error"]
    assert "Start the run again" in failed["error"]
    rerun = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    assert rerun["status"] == "queued"  # a failed run is never reused
    restarted.run_until_idle()
    assert as_analyst.get(f"/runs/{rerun['id']}").json()["status"] == "succeeded"


def test_worker_refuses_other_code_version(as_admin, worker, engine, settings) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    other = build_worker(settings.model_copy(update={"git_commit": "other"}), engine)
    other.run_until_idle()
    run = as_admin.get("/runs").json()[0]
    assert run["status"] == "failed"
    assert "rebuild the worker" in run["error"]


def test_compare_with_baseline_and_refusal_across_data_versions(
    as_admin, as_analyst, worker
) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    run_a = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    worker.run_until_idle()
    compared = as_analyst.get(f"/runs/{run_a['id']}/compare").json()
    assert compared["run_b"]["is_baseline"] is True
    assert compared["cross_data_version"] is False
    row = next(
        r
        for r in compared["rows"]
        if (r["unit_id"], r["group_id"], r["service_id"], r["indicator"])
        == ("A3", "G-OLD", "S-HC", "travel_time_walk_min")
    )
    assert (row["a"]["median"], row["b"]["median"], row["difference"]) == (66, 30, 36)
    import_version(as_admin, "1.1.0")
    worker.run_until_idle()
    baseline_110 = next(
        r
        for r in as_admin.get("/runs", params={"baseline": True}).json()
        if r["package_version"] == "1.1.0"
    )
    refused = as_analyst.get(f"/runs/{run_a['id']}/compare", params={"with": baseline_110["id"]})
    assert refused.status_code == 409
    assert "different data versions" in refused.json()["detail"]


def test_export_csv_and_gpkg(as_admin, as_analyst, worker, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    run = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    worker.run_until_idle()
    csv_zip = zipfile.ZipFile(io.BytesIO(as_analyst.get(f"/runs/{run['id']}/export").content))
    assert set(csv_zip.namelist()) == {
        "results.csv",
        "travel_times.csv",
        "unit_changes.csv",
        "metadata.json",
    }
    meta = json.loads(csv_zip.read("metadata.json"))
    for key in (
        "scenario_id",
        "scenario_version",
        "package_id",
        "package_version",
        "code_version",
        "model_id",
        "model_version",
        "seed",
        "config",
        "input_hash",
    ):
        assert key in meta
    assert meta["notice"] == "Diagnostic model: not a research result"
    assert meta["interval_quantiles"] == [0.05, 0.95]
    assert meta["statistics"]["low"] == "quantile 0.05 of the samples"
    assert "never add medians" in meta["statistics"]["totals"]
    lines = csv_zip.read("results.csv").decode().splitlines()
    assert lines[0] == (
        "unit_id,unit_name,group_id,service_id,time_label,indicator,median,low,high,mean,"
        "baseline,edge_effect_warning"
    )
    assert len(lines) == 1 + 6 * 3 * 2 * 5
    response = as_analyst.get(f"/runs/{run['id']}/export", params={"format": "gpkg"})
    gpkg_zip = zipfile.ZipFile(io.BytesIO(response.content))
    gpkg = tmp_path / "results.gpkg"
    gpkg.write_bytes(gpkg_zip.read("results.gpkg"))
    with sqlite3.connect(gpkg) as db:
        assert db.execute("SELECT count(*) FROM results").fetchone()[0] == len(lines) - 1
        assert db.execute("SELECT srs_id FROM gpkg_geometry_columns").fetchone()[0] == 2100
        assert db.execute("SELECT geom FROM results LIMIT 1").fetchone()[0][:2] == b"GP"
        columns = [c[1] for c in db.execute("PRAGMA table_info(results)")]
        assert {"median", "low", "high", "mean"} <= set(columns)


def test_viewer_sees_shared_results_but_not_private_runs(
    app, as_admin, as_analyst, as_viewer, worker
) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    shared = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    private = as_analyst.post("/scenarios", json={**CLOSE_E02, "visibility": "private"}).json()[
        "id"
    ]
    run_shared = as_analyst.post("/runs", json={"scenario_id": shared}).json()
    run_private = as_analyst.post("/runs", json={"scenario_id": private, "seed": 9}).json()
    worker.run_until_idle()
    assert as_viewer.get(f"/runs/{run_shared['id']}/results").status_code == 200
    assert as_viewer.get(f"/runs/{run_private['id']}").status_code == 404
    assert as_viewer.post(f"/runs/{run_shared['id']}/cancel").status_code == 403


def test_request_handler_only_queues(as_admin, as_analyst, engine) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM run_results")).scalar_one() == 0
        assert conn.execute(text("SELECT status FROM jobs")).scalar_one() == "queued"


def _noise(as_analyst, run_id: str) -> list[dict]:  # type: ignore[no-untyped-def,type-arg]
    rows: list[dict] = as_analyst.get(  # type: ignore[type-arg]
        f"/runs/{run_id}/results", params={"indicator": "diagnostic_noise"}
    ).json()
    return rows


@pytest.mark.parametrize("levels", ["0.05,0.95", "0.25,0.75"])
def test_results_store_mean_median_and_configured_quantiles_from_samples(
    app, as_admin, as_analyst, engine, settings, levels: str
) -> None:  # type: ignore[no-untyped-def]
    from solidaritynode_backend.config import get_settings

    configured = settings.model_copy(update={"result_interval_quantiles": levels})
    app.dependency_overrides[get_settings] = lambda: configured
    worker = build_worker(configured, engine)
    _ready(as_admin, worker)
    low_q, high_q = (float(x) for x in levels.split(","))
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    run = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    assert run["config"]["interval_quantiles"] == [low_q, high_q]  # recorded, part of the hash
    assert run["interval_quantiles"] == [low_q, high_q]
    worker.run_until_idle()
    samples = pq.read_table(
        Path(settings.results_dir) / "runs" / run["id"] / "samples.parquet"
    ).to_pandas()
    rows = _noise(as_analyst, run["id"])
    assert rows
    for row in rows:
        draws = samples[
            (samples.unit_id == row["unit_id"])
            & (samples.group_id == row["group_id"])
            & (samples.service_id == row["service_id"])
            & (samples.indicator == "diagnostic_noise")
        ]["value"].to_numpy(dtype=np.float64)  # stored as float32 (ADR 0008)
        assert len(draws) == 200
        assert row["median"] == pytest.approx(float(np.median(draws)))
        assert row["mean"] == pytest.approx(float(draws.mean()))
        assert row["low"] == pytest.approx(float(np.quantile(draws, low_q)))
        assert row["high"] == pytest.approx(float(np.quantile(draws, high_q)))
    # Deterministic values: median = mean = low = high.
    walk = as_analyst.get(
        f"/runs/{run['id']}/results", params={"indicator": "travel_time_walk_min"}
    ).json()
    assert all(r["median"] == r["mean"] == r["low"] == r["high"] for r in walk)


def test_settings_refuse_bad_interval_quantiles() -> None:
    from solidaritynode_backend.config import Settings

    assert Settings().interval_quantiles() == (0.05, 0.95)
    for bad in ("0.5,0.95", "0.05", "a,b", "0.95,0.05"):
        with pytest.raises(ValueError, match="interval"):
            Settings(result_interval_quantiles=bad)

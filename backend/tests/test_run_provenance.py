"""Seeds, code version, refused cached reuse, environment and storage (ADR 0017)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from tests.conftest import CLOSE_E02, import_version, login


def _ready(as_admin: Any, worker: Any) -> None:
    import_version(as_admin, "1.0.0")
    worker.run_until_idle()


def _samples(settings: Any, run_id: str) -> Path:
    return Path(settings.results_dir) / "runs" / run_id / "samples.parquet"


def test_a_seed_is_drawn_and_recorded_when_none_is_given(as_admin, as_analyst, worker) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    first = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    second = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    for run in (first, second):
        assert run["seed_source"] == "drawn"
        assert 0 <= run["seed"] < 2**31
        assert run["config"]["n_samples"] == 200  # the number of draws is recorded too
    assert first["id"] != second["id"]  # different drawn seeds: different inputs
    given = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 5}).json()
    assert (given["seed"], given["seed_source"]) == (5, "given")
    baseline = next(r for r in as_admin.get("/runs").json() if r["is_baseline"])
    assert (baseline["seed"], baseline["seed_source"]) == (1, "given")  # deterministic baseline


def test_runs_from_unknown_or_dirty_code_carry_a_warning(app, settings, users, engine) -> None:  # type: ignore[no-untyped-def]
    from solidaritynode_backend.config import get_settings
    from solidaritynode_backend.worker import build_worker

    dirty = settings.model_copy(update={"git_commit": "0123456789ab-dirty"})
    app.dependency_overrides[get_settings] = lambda: dirty
    admin = login(app, "admin")
    import_version(admin, "1.0.0")
    build_worker(dirty, engine).run_until_idle()
    baseline = next(r for r in admin.get("/runs").json() if r["is_baseline"])
    assert (baseline["code_version"], baseline["code_version_dirty"]) == (
        "0123456789ab-dirty",
        True,
    )
    clean = settings.model_copy(update={"git_commit": "0123456789ab"})
    app.dependency_overrides[get_settings] = lambda: clean
    sid = admin.post("/scenarios", json=CLOSE_E02).json()["id"]
    assert (
        admin.post("/runs", json={"scenario_id": sid, "seed": 1}).json()["code_version_dirty"]
        is False
    )


def test_cached_reuse_is_refused_when_the_results_file_is_missing_or_damaged(
    as_admin, as_analyst, worker, settings
) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    first = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 1}).json()
    worker.run_until_idle()
    assert as_analyst.post("/runs", json={"scenario_id": sid, "seed": 1}).json()["reused"]

    with _samples(settings, first["id"]).open("ab") as handle:  # damage it
        handle.write(b"x")
    second = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 1})
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]
    assert "failed the integrity check" in second.json()["reuse_refused"]
    assert first["id"] in second.json()["reuse_refused"]
    worker.run_until_idle()
    # The new, valid run is reused from now on (not re-run again and again).
    third = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 1}).json()
    assert (third["id"], third["reused"]) == (second.json()["id"], True)

    _samples(settings, second.json()["id"]).unlink()  # and a missing file
    _samples(settings, first["id"]).unlink()
    fourth = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 1}).json()
    assert fourth["reused"] is False
    assert "missing" in fourth["reuse_refused"]


def test_environment_is_recorded_and_exported_outside_the_hash(
    as_admin, as_analyst, worker
) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    queued = as_analyst.post("/runs", json={"scenario_id": sid, "seed": 1}).json()
    assert queued["environment"] is None  # set by the worker when it runs
    worker.run_until_idle()
    run = as_analyst.get(f"/runs/{queued['id']}").json()
    assert run["environment"]["numpy"] == np.__version__
    assert run["environment"]["python"].startswith("3.12")
    assert run["input_hash"] == queued["input_hash"]
    archive = zipfile.ZipFile(io.BytesIO(as_analyst.get(f"/runs/{run['id']}/export").content))
    meta = json.loads(archive.read("metadata.json"))
    assert meta["environment"] == run["environment"]
    assert (meta["seed"], meta["seed_source"]) == (1, "given")
    assert meta["config"]["n_samples"] == 200


def test_admin_sees_results_disk_usage(as_admin, as_analyst, worker, settings) -> None:  # type: ignore[no-untyped-def]
    _ready(as_admin, worker)
    storage = as_admin.get("/storage").json()
    assert storage["runs_with_samples"] == 1  # the baseline
    assert storage["samples_files"] == 1
    assert storage["samples_bytes"] > 0
    assert storage["free_bytes"] > 0
    assert as_analyst.get("/storage").status_code == 403

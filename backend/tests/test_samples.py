"""Samples file: joint draws, layout, metadata, integrity and size estimate (ADR 0008)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from solidaritynode_core.uncertainty import summarise_total

from solidaritynode_backend.services.samples import (
    RESULTS_SCHEMA_VERSION,
    SamplesIntegrityError,
    file_sha256,
    read_samples,
)
from tests.conftest import CLOSE_E02, import_version

ROWS = 6 * 3 * 2 * 200  # core units x groups x services x draws of diagnostic_noise


def _run(as_admin: Any, as_analyst: Any, worker: Any) -> dict[str, Any]:
    import_version(as_admin, "1.0.0")
    worker.run_until_idle()
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    run: dict[str, Any] = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    worker.run_until_idle()
    done: dict[str, Any] = as_analyst.get(f"/runs/{run['id']}").json()
    return done


def _path(settings: Any, run_id: str) -> Path:
    return Path(settings.results_dir) / "runs" / run_id / "samples.parquet"


def test_layout_metadata_and_checksum(as_admin, as_analyst, worker, settings) -> None:  # type: ignore[no-untyped-def]
    run = _run(as_admin, as_analyst, worker)
    path = _path(settings, run["id"])
    assert run["samples_sha256"] == file_sha256(path)
    meta = {k.decode(): v.decode() for k, v in (pq.read_schema(path).metadata or {}).items()}
    assert meta["solidaritynode.run_id"] == run["id"]
    assert meta["solidaritynode.model_id"] == "diagnostic-v0"
    assert meta["solidaritynode.model_version"] == run["model_version"] == "0.2.1"
    assert meta["solidaritynode.package_id"] == run["package_id"]
    assert meta["solidaritynode.package_version"] == "1.0.0"
    assert meta["solidaritynode.data_version_id"] == str(run["data_version_id"])
    assert meta["solidaritynode.results_schema_version"] == RESULTS_SCHEMA_VERSION
    assert meta["solidaritynode.value_dtype"] == "float32"
    table = read_samples(path, run["samples_sha256"], run["id"])
    assert table.num_rows == ROWS
    for name in ("unit_id", "group_id", "service_id", "time_label", "indicator"):
        assert pa.types.is_dictionary(table.schema.field(name).type), name
    assert table.schema.field("value").type == pa.float32()
    assert table.schema.field("sample").type == pa.int32()
    keys = list(
        zip(
            *(
                table.column(c).to_pylist()
                for c in ("indicator", "unit_id", "group_id", "service_id", "time_label", "sample")
            ),
            strict=True,
        )
    )
    assert keys == sorted(keys)
    column_meta = pq.ParquetFile(path).metadata.row_group(0)
    assert {column_meta.column(i).compression for i in range(column_meta.num_columns)} == {"ZSTD"}


def test_totals_across_units_use_the_same_sample_index(
    as_admin, as_analyst, worker, settings
) -> None:  # type: ignore[no-untyped-def]
    run = _run(as_admin, as_analyst, worker)
    frame = read_samples(_path(settings, run["id"]), run["samples_sha256"], run["id"]).to_pandas()
    one = frame[(frame.group_id == "G-OLD") & (frame.service_id == "S-HC")]
    parts = [
        g.sort_values("sample")["value"].to_numpy(dtype=np.float64)
        for _, g in one.groupby("unit_id", observed=True)
    ]
    assert len(parts) == 6
    by_index = one.groupby("sample", observed=True)["value"].sum().to_numpy(dtype=np.float64)
    total = summarise_total(parts)
    assert total.median == pytest.approx(float(np.median(by_index)), abs=1e-5)
    assert total.n_samples == 200


def test_damaged_or_foreign_file_is_refused_on_read_and_export(
    as_admin, as_analyst, worker, settings
) -> None:  # type: ignore[no-untyped-def]
    run = _run(as_admin, as_analyst, worker)
    path = _path(settings, run["id"])
    with pytest.raises(SamplesIntegrityError, match="belongs to run"):
        read_samples(path, None, "another-run")
    with path.open("ab") as handle:
        handle.write(b"x")
    with pytest.raises(SamplesIntegrityError, match="SHA-256"):
        read_samples(path, run["samples_sha256"], run["id"])
    response = as_analyst.get(f"/runs/{run['id']}/export")
    assert response.status_code == 409
    assert "damaged or changed" in response.json()["detail"]
    path.unlink()
    assert "missing" in as_analyst.get(f"/runs/{run['id']}/export").json()["detail"]


def test_samples_size_is_estimated_before_the_run_and_warned(
    app, as_admin, as_analyst, worker, settings
) -> None:  # type: ignore[no-untyped-def]
    from solidaritynode_backend.config import get_settings

    import_version(as_admin, "1.0.0")
    worker.run_until_idle()
    small_limit = settings.model_copy(update={"samples_warn_mb": 0.1})
    app.dependency_overrides[get_settings] = lambda: small_limit
    sid = as_analyst.post("/scenarios", json=CLOSE_E02).json()["id"]
    run = as_analyst.post("/runs", json={"scenario_id": sid}).json()
    assert run["status"] == "queued"  # still queued: the estimate only warns
    # 6 core units x 3 groups x 2 services x 1 sampled indicator x 200 draws, 28 bytes per row.
    assert run["samples_estimate_bytes"] == ROWS * 28
    assert run["samples_limit_bytes"] == 100_000
    assert run["samples_estimate_bytes"] > run["samples_limit_bytes"]

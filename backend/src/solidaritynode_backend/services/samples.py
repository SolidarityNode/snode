"""Per-sample results in Parquet: layout, metadata, integrity and size estimate (ADR 0008).

One file per run, ``<results_dir>/runs/<run_id>/samples.parquet``, long format with columns
``unit_id, group_id, service_id, time_label, indicator, sample, value``:

* ``sample`` is the index of one **joint** Monte Carlo draw shared by every cell of the run
  (registry contract), so totals are computed sample by sample;
* id columns are dictionary-encoded; ``value`` is ``float32`` unless the model declares
  ``float64`` (``ModelSpec.sample_dtype``);
* rows are sorted by indicator, unit, group, service, time and sample; zstd compression;
* the Parquet key-value metadata records the run id, model id and version, data package and
  version, data version id, results schema version and value precision;
* the file's SHA-256 is stored on the run row and verified on every read and export.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from solidaritynode_core.model import ModelResult, ModelSpec
from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.messages import msg

__all__ = [
    "META_PREFIX",
    "RESULTS_SCHEMA_VERSION",
    "SamplesIntegrityError",
    "as_stored",
    "estimate_samples_bytes",
    "file_sha256",
    "read_samples",
    "verify_samples",
    "write_samples",
]

RESULTS_SCHEMA_VERSION = "1"
"""Version of the samples file layout described in this module."""
META_PREFIX = "solidaritynode."
ID_COLUMNS = ("unit_id", "group_id", "service_id", "time_label", "indicator")
_SORT = ("indicator", "unit_id", "group_id", "service_id", "time_label", "sample")
# Upper bound per row before compression: five dictionary indices and the sample index (int32)
# plus the value. The estimate is deliberately conservative.
_ROW_OVERHEAD_BYTES = 6 * 4
_VALUE_BYTES = {"float32": 4, "float64": 8}


class SamplesIntegrityError(RuntimeError):
    """The samples file is missing, or its checksum or metadata differ from the run's record."""


def file_sha256(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def as_stored(result: ModelResult, dtype: str) -> ModelResult:
    """Return ``result`` with its samples rounded to the stored precision.

    Summary statistics are computed from these values, so they can be reproduced exactly from
    the file.
    """
    if dtype == "float64":
        return result
    return replace(
        result,
        samples=tuple(
            replace(s, values=np.asarray(s.values, dtype=dtype).astype(np.float64))
            for s in result.samples
        ),
    )


def write_samples(result: ModelResult, path: Path, metadata: Mapping[str, str], dtype: str) -> str:
    """Write the samples of ``result`` to ``path`` atomically and return the file's SHA-256."""
    cells = sorted(result.samples, key=lambda s: (s.indicator, s.unit, s.group, s.service, s.time))
    lengths = [len(c.values) for c in cells]
    ids = {
        "unit_id": [c.unit for c in cells],
        "group_id": [c.group for c in cells],
        "service_id": [c.service for c in cells],
        "time_label": [c.time for c in cells],
        "indicator": [c.indicator for c in cells],
    }
    columns: dict[str, pa.Array[Any]] = {
        name: pa.array(
            np.repeat(np.asarray(values, dtype=object), lengths), pa.string()
        ).dictionary_encode()
        for name, values in ids.items()
    }
    columns["sample"] = pa.array(np.concatenate([np.arange(n) for n in lengths]), pa.int32())
    columns["value"] = pa.array(
        np.concatenate([np.asarray(c.values, dtype=dtype) for c in cells]),
        pa.float32() if dtype == "float32" else pa.float64(),
    )
    table = pa.table(
        {**{k: columns[k] for k in ID_COLUMNS}, **{k: columns[k] for k in ("sample", "value")}}
    )
    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            **{f"{META_PREFIX}{k}".encode(): str(v).encode() for k, v in metadata.items()},
            f"{META_PREFIX}results_schema_version".encode(): RESULTS_SCHEMA_VERSION.encode(),
            f"{META_PREFIX}value_dtype".encode(): dtype.encode(),
            f"{META_PREFIX}sort".encode(): ",".join(_SORT).encode(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    digest = file_sha256(tmp)
    tmp.replace(path)
    return digest


def read_samples(path: str | Path, sha256: str | None, run_id: str) -> pa.Table:
    """Read a run's samples after checking the file against the run's record.

    Args:
        path: The run's ``samples_path``.
        sha256: The run's ``samples_sha256``; ``None`` for runs stored before checksums (not
            checked).
        run_id: The run's id, compared with the file metadata when present.

    Raises:
        SamplesIntegrityError: If the file is missing, its checksum differs or it belongs to
            another run.
    """
    verify_samples(path, sha256, run_id)
    return pq.read_table(path)


def verify_samples(path: str | Path, sha256: str | None, run_id: str) -> None:
    """Check a run's samples file without loading it (see :func:`read_samples`)."""
    file = Path(path)
    if not file.is_file():
        raise SamplesIntegrityError(msg("error.samples_missing", run=run_id, file=file))
    if sha256 is not None and file_sha256(file) != sha256:
        raise SamplesIntegrityError(msg("error.samples_mismatch", run=run_id))
    meta = pq.read_schema(file).metadata or {}
    recorded = meta.get(f"{META_PREFIX}run_id".encode())
    if recorded is not None and recorded.decode() != run_id:
        raise SamplesIntegrityError(
            msg("error.samples_other_run", file=file, other=recorded.decode(), run=run_id)
        )


def estimate_samples_bytes(
    db: Session, model: ModelSpec, data_version_id: int, n_samples: int
) -> int:
    """Estimate (upper bound, before compression) the samples file size of a run.

    Rows = draws × core units × groups × services × sampled (non-deterministic) indicators of
    the model, for static results.
    """
    sampled = sum(1 for i in model.indicators if not i.deterministic)
    if sampled == 0 or n_samples <= 0:
        return 0
    units, groups, services = db.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM data_features WHERE data_version_id = :dv
                 AND layer = 'spatial_units' AND properties->>'role' = 'core'),
              (SELECT count(*) FROM data_records WHERE data_version_id = :dv
                 AND table_name = 'groups'),
              (SELECT count(*) FROM data_records WHERE data_version_id = :dv
                 AND table_name = 'services')
            """
        ),
        {"dv": data_version_id},
    ).one()
    rows = n_samples * int(units) * int(groups) * int(services) * sampled
    return rows * (_ROW_OVERHEAD_BYTES + _VALUE_BYTES[model.sample_dtype])

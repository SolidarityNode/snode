"""Export a run's results as CSV or GeoPackage, zipped with ``metadata.json``.

The metadata file holds every reproducibility field of the run (ADR 0017): scenario id and
version, data package id and version, code version, model id and version, seed, configuration,
input hash, timestamps, and the diagnostic label when the model is diagnostic. The GeoPackage is
written with the shared standard-library writer (:mod:`solidaritynode_backend.gpkg`); geometries
are the spatial units of the run's data version in the package CRS, from PostGIS.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from solidaritynode_core.validation import DIAGNOSTIC_LABEL
from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.gpkg import Srs, blob_from_wkb, write_geopackage
from solidaritynode_backend.orm import DataVersion, Run

__all__ = ["export_csv", "export_gpkg"]

RESULT_COLUMNS = (
    "unit_id",
    "unit_name",
    "group_id",
    "service_id",
    "time_label",
    "indicator",
    "median",
    "low",
    "high",
    "mean",
    "baseline",
    "edge_effect_warning",
)


def _csv_text(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in columns})
    return buffer.getvalue()


def _metadata(meta: Mapping[str, Any]) -> str:
    content = dict(meta)
    if content.get("diagnostic"):
        content["notice"] = DIAGNOSTIC_LABEL
    levels = content.get("interval_quantiles")
    content["statistics"] = {
        "median": "median of the samples (central value shown in the application)",
        "low": f"quantile {levels[0]} of the samples" if levels else "lower interval bound",
        "high": f"quantile {levels[1]} of the samples" if levels else "upper interval bound",
        "mean": "mean of the samples",
        "deterministic values": "median = low = high = mean = the value",
        "totals": "compute from samples.parquet draw by draw; never add medians or bounds",
    }
    return json.dumps(content, indent=2, sort_keys=True, default=str) + "\n"


def _tables(db: Session, run: Run) -> dict[str, list[dict[str, Any]]]:
    return {
        name: list(rows)
        for name, rows in db.execute(
            text("SELECT table_name, rows FROM run_tables WHERE run_id = :r"), {"r": run.id}
        )
    }


def export_csv(
    db: Session, run: Run, meta: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> bytes:
    """Return a zip with ``results.csv``, model tables as CSV and ``metadata.json``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("results.csv", _csv_text(rows, RESULT_COLUMNS))
        for name, table in sorted(_tables(db, run).items()):
            columns = list(table[0]) if table else []
            flat = [
                {k: ("; ".join(v) if isinstance(v, list) else v) for k, v in r.items()}
                for r in table
            ]
            archive.writestr(f"{name}.csv", _csv_text(flat, columns))
        archive.writestr("metadata.json", _metadata(meta))
    return buffer.getvalue()


RESULT_TYPES = {
    "median": "REAL",
    "low": "REAL",
    "high": "REAL",
    "mean": "REAL",
    "baseline": "REAL",
    "edge_effect_warning": "BOOLEAN",
}


def _write_gpkg(
    path: Path,
    srid: int,
    srs_wkt: str,
    features: Sequence[tuple[tuple[bytes, tuple[float, float, float, float]], Mapping[str, Any]]],
) -> None:
    columns = [(c, RESULT_TYPES.get(c, "TEXT")) for c in RESULT_COLUMNS]
    write_geopackage(
        path,
        [Srs(f"EPSG:{srid}", srid, "EPSG", srid, srs_wkt)],
        [
            (
                "results",
                "GEOMETRY",
                srid,
                "Run results per core unit (median, interval, mean; ADR 0017)",
                columns,
                [
                    (blob_from_wkb(wkb, srid, env), [row.get(c) for c, _ in columns])
                    for (wkb, env), row in features
                ],
            )
        ],
        datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    )


def export_gpkg(
    db: Session, run: Run, meta: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> bytes:
    """Return a zip with ``results.gpkg`` (layer ``results``) and ``metadata.json``."""
    dv = db.get(DataVersion, run.data_version_id)
    assert dv is not None
    geoms = {
        fid: (bytes(wkb), (x0, x1, y0, y1))
        for fid, wkb, x0, x1, y0, y1 in db.execute(
            text(
                "SELECT feature_id, ST_AsBinary(geom, 'NDR'), ST_XMin(geom), ST_XMax(geom), "
                "ST_YMin(geom), ST_YMax(geom) FROM data_features "
                "WHERE data_version_id = :dv AND layer = 'spatial_units'"
            ),
            {"dv": dv.id},
        )
    }
    srs_wkt = (
        db.scalar(text("SELECT srtext FROM spatial_ref_sys WHERE srid = :s"), {"s": dv.srid})
        or "undefined"
    )
    features = [(geoms[r["unit_id"]], r) for r in rows if r["unit_id"] in geoms]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "results.gpkg"
        _write_gpkg(path, dv.srid, srs_wkt, features)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(path, "results.gpkg")
            archive.writestr("metadata.json", _metadata(meta))
    return buffer.getvalue()

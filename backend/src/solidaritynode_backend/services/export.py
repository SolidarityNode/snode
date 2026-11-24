"""Export a run's results as CSV or GeoPackage, zipped with ``metadata.json``.

The metadata file holds every reproducibility field of the run (ADR 0017): scenario id and
version, data package id and version, code version, model id and version, seed, configuration,
input hash, timestamps, and the diagnostic label when the model is diagnostic. The GeoPackage is
written with the standard library (``sqlite3``); geometries are the spatial units of the run's
data version in the package CRS, from PostGIS.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import struct
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from solidaritynode_core.validation import DIAGNOSTIC_LABEL
from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.orm import DataVersion, Run

__all__ = ["export_csv", "export_gpkg"]

RESULT_COLUMNS = (
    "unit_id",
    "unit_name",
    "group_id",
    "service_id",
    "time_label",
    "indicator",
    "value",
    "low",
    "high",
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


def _gpkg_blob(wkb: bytes, srid: int) -> bytes:
    # GeoPackage binary header: magic, version 0, flags (little endian, no envelope), SRS id.
    return b"GP" + bytes([0, 0b0000_0001]) + struct.pack("<i", srid) + wkb


def _write_gpkg(
    path: Path, srid: int, srs_wkt: str, features: Sequence[tuple[bytes, Mapping[str, Any]]]
) -> None:
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA application_id = 1196444487")  # 'GPKG'
        db.execute("PRAGMA user_version = 10400")
        db.executescript(
            """
            CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY,
              organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
              definition TEXT NOT NULL, description TEXT);
            CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY,
              data_type TEXT NOT NULL, identifier TEXT UNIQUE, description TEXT DEFAULT '',
              last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
              srs_id INTEGER REFERENCES gpkg_spatial_ref_sys(srs_id));
            CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL,
              m TINYINT NOT NULL, CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name));
            """
        )
        db.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
                ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
                (f"EPSG:{srid}", srid, "EPSG", srid, srs_wkt, None),
            ],
        )
        db.execute(
            """CREATE TABLE results (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom POLYGON,
            unit_id TEXT, unit_name TEXT, group_id TEXT, service_id TEXT, time_label TEXT,
            indicator TEXT, value REAL, low REAL, high REAL, baseline REAL,
            edge_effect_warning BOOLEAN)"""
        )
        db.execute(
            "INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) "
            "VALUES ('results', 'features', 'results', ?)",
            (srid,),
        )
        db.execute(
            "INSERT INTO gpkg_geometry_columns VALUES ('results', 'geom', 'POLYGON', ?, 0, 0)",
            (srid,),
        )
        db.executemany(
            "INSERT INTO results (geom, unit_id, unit_name, group_id, service_id, time_label, "
            "indicator, value, low, high, baseline, edge_effect_warning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (_gpkg_blob(wkb, srid), *(row.get(c) for c in RESULT_COLUMNS))
                for wkb, row in features
            ],
        )


def export_gpkg(
    db: Session, run: Run, meta: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> bytes:
    """Return a zip with ``results.gpkg`` (layer ``results``) and ``metadata.json``."""
    dv = db.get(DataVersion, run.data_version_id)
    assert dv is not None
    geoms = {
        fid: bytes(wkb)
        for fid, wkb in db.execute(
            text(
                "SELECT feature_id, ST_AsBinary(geom, 'NDR') FROM data_features "
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

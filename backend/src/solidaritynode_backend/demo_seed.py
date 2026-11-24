"""Load the synthetic demo dataset into the temporary ``demo`` schema (``make seed``).

The loader **copies** files into tables; it computes nothing (no travel times, capacities or
any other method). It verifies the manifest checksums first, then replaces the contents of
every ``demo`` table in one transaction, so running it twice gives the same state
(idempotent). Data: ``data/synthetic/demo/`` (DP-001). Schema: migration ``0002``.

**Temporary:** replaced by data-package import in the platform PR (ADR 0013).

Usage::

    python -m solidaritynode_backend.demo_seed [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import struct
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from solidaritynode_backend.config import get_settings

__all__ = [
    "DemoData",
    "ManifestError",
    "gpkg_to_wkb",
    "load_demo",
    "main",
    "read_gpkg_layer",
    "seed",
    "verify_manifest",
]

SRID = 2100
SCHEMA = "demo"

# Insertion order respects foreign keys; deletion runs in reverse.
TABLE_ORDER = (
    "package",
    "municipalities",
    "spatial_units",
    "population_groups",
    "population",
    "services",
    "facilities",
    "facility_services",
    "network_nodes",
    "network_edges",
    "hand_check_travel_times",
    "scenarios",
)

_GEOM = f"ST_GeomFromWKB(:{{name}}, {SRID})"


class ManifestError(ValueError):
    """The demo files do not match ``manifest.json``."""


def gpkg_to_wkb(blob: bytes) -> bytes:
    """Strip the GeoPackage binary header and return the standard WKB geometry.

    Args:
        blob: A GeoPackage geometry blob (``GP`` magic, version, flags, SRS id, envelope, WKB).

    Returns:
        The WKB part.

    Raises:
        ValueError: If the blob is not a GeoPackage geometry or is empty.
    """
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry blob")
    flags = blob[3]
    if flags & 0b0001_0000:
        raise ValueError("empty geometry")
    envelope_doubles = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}[(flags >> 1) & 0b111]
    return blob[8 + 8 * envelope_doubles :]


def gpkg_srs_id(blob: bytes) -> int:
    """Return the SRS id stored in a GeoPackage geometry header."""
    order = "<" if blob[3] & 1 else ">"
    return int(struct.unpack(f"{order}i", blob[4:8])[0])


def read_gpkg_layer(path: Path, layer: str) -> list[dict[str, Any]]:
    """Read a GeoPackage feature table with the standard library.

    Args:
        path: GeoPackage file.
        layer: Feature table name (must be listed in ``gpkg_contents``).

    Returns:
        One dict per feature; the geometry is returned as WKB under ``geom``.
    """
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        known = {r[0] for r in db.execute("SELECT table_name FROM gpkg_contents")}
        if layer not in known:
            raise ValueError(f"layer {layer!r} not in {path.name}")
        db.row_factory = sqlite3.Row
        rows = db.execute(f'SELECT * FROM "{layer}"').fetchall()
    out = []
    for row in rows:
        record = {k: row[k] for k in row.keys() if k != "fid"}  # noqa: SIM118 - Row API
        blob = record["geom"]
        if gpkg_srs_id(blob) != SRID:
            raise ValueError(f"{layer}: expected EPSG:{SRID}")
        record["geom"] = gpkg_to_wkb(blob)
        out.append(record)
    return out


def verify_manifest(data_dir: Path) -> dict[str, Any]:
    """Check that every file listed in ``manifest.json`` exists with the stated SHA-256.

    Returns:
        The parsed manifest.

    Raises:
        ManifestError: On a missing file or checksum mismatch.
    """
    manifest: dict[str, Any] = json.loads((data_dir / "manifest.json").read_text("utf-8"))
    for entry in manifest["files"]:
        path = data_dir / entry["path"]
        if not path.is_file():
            raise ManifestError(f"missing file {entry['path']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ManifestError(f"checksum mismatch for {entry['path']}")
    return manifest


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _none(value: str) -> str | None:
    return value or None


@dataclass(frozen=True)
class DemoData:
    """Rows per ``demo`` table, ready to insert. Built from files only; nothing is computed."""

    rows: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        """Return the number of rows per table."""
        return {table: len(self.rows.get(table, ())) for table in TABLE_ORDER}


def load_demo(data_dir: Path) -> DemoData:
    """Read and verify the demo dataset into rows per table.

    Args:
        data_dir: Directory of the demo dataset (``data/synthetic/demo``).

    Returns:
        The rows to insert.
    """
    manifest = verify_manifest(data_dir)
    gpkg = data_dir / "demo.gpkg"
    centroids = {c["unit_id"]: c for c in read_gpkg_layer(gpkg, "unit_centroids")}
    scenarios = [
        json.loads(p.read_text("utf-8")) for p in sorted((data_dir / "scenarios").glob("*.json"))
    ]
    rows: dict[str, list[dict[str, Any]]] = {
        "package": [
            {
                "package_id": manifest["package_id"],
                "version": manifest["version"],
                "manifest": json.dumps(manifest),
            }
        ],
        "municipalities": read_gpkg_layer(gpkg, "municipalities"),
        "spatial_units": [
            {
                **u,
                "centroid_node_id": centroids[u["unit_id"]]["node_id"],
                "centroid": centroids[u["unit_id"]]["geom"],
            }
            for u in read_gpkg_layer(gpkg, "spatial_units")
        ],
        "population_groups": [dict(r) for r in _csv(data_dir / "groups.csv")],
        "population": [
            {**r, "population": int(r["population"])} for r in _csv(data_dir / "population.csv")
        ],
        "services": [
            {**r, "max_acceptable_wait": _none(r["max_acceptable_wait"])}
            for r in _csv(data_dir / "services.csv")
        ],
        "facilities": read_gpkg_layer(gpkg, "facilities"),
        "facility_services": [
            {
                "facility_id": r["facility_id"],
                "service_id": r["service_id"],
                **{k: float(r[k]) if r[k] else None for k in ("places", "staff", "throughput")},
            }
            for r in _csv(data_dir / "facility_services.csv")
        ],
        "network_nodes": [
            {
                "node_id": r["node_id"],
                "kind": r["kind"],
                "geom": struct.pack("<BIdd", 1, 1, float(r["x"]), float(r["y"])),
            }
            for r in _csv(data_dir / "network_nodes.csv")
        ],
        "network_edges": [
            {
                **r,
                "length_m": float(r["length_m"]),
                "travel_time_min": float(r["travel_time_min"]),
                "closable": r["closable"] == "true",
            }
            for r in _csv(data_dir / "network_edges.csv")
        ],
        "hand_check_travel_times": [
            {**r, "travel_time_min": float(r["travel_time_min"])}
            for r in _csv(data_dir / "hand_check_travel_times.csv")
        ],
        "scenarios": [
            {"scenario_id": s["id"], "version": int(s["version"]), "body": json.dumps(s)}
            for s in scenarios
        ],
    }
    return DemoData(rows)


_GEOMETRY_COLUMNS = {"geom", "centroid"}
_CASTS = {
    "manifest": "CAST(:manifest AS jsonb)",
    "body": "CAST(:body AS jsonb)",
    "max_acceptable_wait": "CAST(:max_acceptable_wait AS interval)",  # ISO 8601, e.g. P7D
}


def _insert_sql(table: str, columns: Sequence[str]) -> str:
    values = []
    for c in columns:
        if c in _GEOMETRY_COLUMNS:
            values.append(_GEOM.format(name=c))
        else:
            values.append(_CASTS.get(c, f":{c}"))
    return f"INSERT INTO {SCHEMA}.{table} ({', '.join(columns)}) VALUES ({', '.join(values)})"


def seed(connection: Connection, data: DemoData) -> dict[str, int]:
    """Replace the contents of the ``demo`` schema with ``data`` (idempotent).

    Runs on the given connection; the caller owns the transaction.

    Returns:
        Rows inserted per table.
    """
    tables = ", ".join(f"{SCHEMA}.{t}" for t in TABLE_ORDER)
    connection.execute(text(f"TRUNCATE {tables}"))
    for table in TABLE_ORDER:
        rows = data.rows.get(table, ())
        if rows:
            connection.execute(text(_insert_sql(table, list(rows[0]))), list(rows))
    return data.counts()


def main(argv: Sequence[str] | None = None, engine: Engine | None = None) -> int:
    """Command-line entry point used by ``make seed``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=None, help="demo dataset directory")
    args = parser.parse_args(argv)
    data_dir: Path = args.data_dir or get_settings().demo_data_dir
    try:
        data = load_demo(data_dir)
    except (OSError, ManifestError, ValueError) as exc:
        print(f"seed: cannot read demo dataset in {data_dir}: {exc}", file=sys.stderr)
        return 1
    engine = engine or create_engine(get_settings().database_url.get_secret_value())
    with engine.begin() as connection:
        counts = seed(connection, data)
    print(f"seed: loaded synthetic demo dataset from {data_dir} into schema '{SCHEMA}':")
    for table, n in counts.items():
        print(f"  {SCHEMA}.{table:<24} {n:>4} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

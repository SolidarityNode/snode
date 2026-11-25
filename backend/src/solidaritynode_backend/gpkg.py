"""Minimal GeoPackage writer and reader, standard library only (``sqlite3``, ``struct``).

Shared by the demo data scripts (``scripts/``, run without a virtual environment), the data
package import (ADR 0013) and the GeoPackage export. Moved here from the bootstrap writer of
``scripts/generate_demo_data.py``; that script's output is unchanged.

Supported: feature tables with one geometry column ``geom`` of type POINT, LINESTRING, POLYGON,
MULTIPOINT, MULTILINESTRING or MULTIPOLYGON (2D), attribute columns of type TEXT, INTEGER,
REAL/DOUBLE, BOOLEAN or DATE, in any CRS declared in ``gpkg_spatial_ref_sys``. Geometries are
exchanged as GeoJSON-like dicts (``{"type": ..., "coordinates": ...}``) for writing and as
standard little-endian WKB for reading.

**Reproducible files.** With ``reproducible=True`` the writer fixes the SQLite header field that
records the library version (offset 96), so the same content gives the same bytes on any
SQLite version; data package checksums rely on this.
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "APPLICATION_ID",
    "GeoPackageError",
    "Layer",
    "Srs",
    "blob_from_wkb",
    "encode_geometry",
    "read_geopackage",
    "write_geopackage",
]

APPLICATION_ID = 0x47504B47  # 'GPKG'
USER_VERSION = 10400  # GeoPackage 1.4
_FIXED_SQLITE_VERSION = 3_045_000  # written at header offset 96 for reproducible files
_WKB_TYPES = {
    "Point": 1,
    "LineString": 2,
    "Polygon": 3,
    "MultiPoint": 4,
    "MultiLineString": 5,
    "MultiPolygon": 6,
}
_WKB_NAMES = {v: k for k, v in _WKB_TYPES.items()}
GEOMETRY_TYPES = frozenset(name.upper() for name in _WKB_TYPES) | {"GEOMETRY"}
_UNDEFINED_SRS = (
    ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
    ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
)


# Exact text of the bootstrap schema: SQLite stores it verbatim, so it is part of the file bytes.
_SCHEMA_SQL = (
    "\n"
    "        CREATE TABLE gpkg_spatial_ref_sys (\n"
    "          srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,\n"
    "          organization_coordsys_id INTEGER NOT NULL, "
    "definition TEXT NOT NULL, description TEXT);\n"
    "        CREATE TABLE gpkg_contents (\n"
    "          table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,\n"
    "          identifier TEXT UNIQUE, description TEXT DEFAULT '',\n"
    "          last_change DATETIME NOT NULL, min_x DOUBLE, min_y DOUBLE, "
    "max_x DOUBLE, max_y DOUBLE,\n"
    "          srs_id INTEGER, CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)\n"
    "          REFERENCES gpkg_spatial_ref_sys(srs_id));\n"
    "        CREATE TABLE gpkg_geometry_columns (\n"
    "          table_name TEXT NOT NULL, column_name TEXT NOT NULL, "
    "geometry_type_name TEXT NOT NULL,\n"
    "          srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,\n"
    "          CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),\n"
    "          CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),\n"
    "          CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) "
    "REFERENCES gpkg_spatial_ref_sys (srs_id));\n"
    "        "
)


class GeoPackageError(ValueError):
    """The file is not a GeoPackage this module can read, with the reason."""


@dataclass(frozen=True, slots=True)
class Srs:
    """A spatial reference system row of ``gpkg_spatial_ref_sys``."""

    name: str
    srs_id: int
    organization: str
    organization_coordsys_id: int
    definition: str


@dataclass(frozen=True, slots=True)
class Layer:
    """A feature table read from a GeoPackage.

    Attributes:
        name: Table name.
        geometry_type: Declared geometry type (for example ``POLYGON``).
        srs: CRS of the geometry column.
        columns: Attribute columns as ``(name, declared type)``, without ``fid`` and ``geom``.
        rows: ``(attributes, wkb)`` per feature; ``wkb`` is little-endian WKB or ``None``.
    """

    name: str
    geometry_type: str
    srs: Srs
    columns: tuple[tuple[str, str], ...]
    rows: tuple[tuple[dict[str, Any], bytes | None], ...]


# --- WKB ---------------------------------------------------------------------------------------


def _points(coords: Sequence[Sequence[float]]) -> bytes:
    return struct.pack("<I", len(coords)) + b"".join(
        struct.pack("<dd", float(c[0]), float(c[1])) for c in coords
    )


def _wkb(kind: str, coords: Sequence[Any]) -> bytes:
    head = struct.pack("<BI", 1, _WKB_TYPES[kind])
    if kind == "Point":
        return head + struct.pack("<dd", float(coords[0]), float(coords[1]))
    if kind == "LineString":
        return head + _points(coords)
    if kind == "Polygon":
        return head + struct.pack("<I", len(coords)) + b"".join(_points(r) for r in coords)
    part = kind.removeprefix("Multi")
    return head + struct.pack("<I", len(coords)) + b"".join(_wkb(part, c) for c in coords)


def _flatten(kind: str, coords: Sequence[Any]) -> list[Sequence[float]]:
    if kind == "Point":
        return [coords]
    if kind in ("LineString", "MultiPoint"):
        return list(coords)
    if kind in ("Polygon", "MultiLineString"):
        return [p for ring in coords for p in ring]
    return [p for poly in coords for ring in poly for p in ring]


def encode_geometry(
    geometry: Mapping[str, Any], srs_id: int, envelope: bool | None = None
) -> tuple[bytes, tuple[float, float, float, float]]:
    """Encode a GeoJSON-like geometry as a GeoPackage blob.

    Args:
        geometry: ``{"type": "Polygon", "coordinates": [...]}`` (2D).
        srs_id: SRS id written in the blob header.
        envelope: Write the XY envelope in the header; default: for every type but Point.

    Returns:
        The blob and the envelope ``(min_x, max_x, min_y, max_y)``.
    """
    kind = str(geometry["type"])
    if kind not in _WKB_TYPES:
        raise GeoPackageError(f"unsupported geometry type {kind}")
    coords = geometry["coordinates"]
    xs = [float(p[0]) for p in _flatten(kind, coords)]
    ys = [float(p[1]) for p in _flatten(kind, coords)]
    env = (min(xs), max(xs), min(ys), max(ys))
    with_env = kind != "Point" if envelope is None else envelope
    flags = 0b0000_0001 | ((1 if with_env else 0) << 1)
    head = b"GP" + bytes([0, flags]) + struct.pack("<i", srs_id)
    if with_env:
        head += struct.pack("<dddd", *env)
    return head + _wkb(kind, coords), env


def blob_from_wkb(
    wkb: bytes, srs_id: int, envelope: tuple[float, float, float, float]
) -> tuple[bytes, tuple[float, float, float, float]]:
    """Wrap WKB (for example from PostGIS ``ST_AsBinary``) in a GeoPackage blob with envelope.

    ``envelope`` is ``(min_x, max_x, min_y, max_y)``; the result can be passed as a row geometry
    to :func:`write_geopackage`.
    """
    head = b"GP" + bytes([0, 0b0000_0011]) + struct.pack("<i", srs_id)
    return head + struct.pack("<dddd", *envelope) + wkb, envelope


def _blob_to_wkb(blob: bytes, where: str) -> bytes | None:
    if len(blob) < 8 or blob[:2] != b"GP":
        raise GeoPackageError(f"{where}: geometry is not a GeoPackage blob")
    if blob[2] != 0:
        raise GeoPackageError(f"{where}: unsupported GeoPackage blob version {blob[2]}")
    flags = blob[3]
    if flags & 0b0010_0000:
        raise GeoPackageError(f"{where}: extended GeoPackage geometries are not supported")
    if flags & 0b0001_0000:
        return None  # empty geometry
    envelope_bytes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((flags >> 1) & 0b111)
    if envelope_bytes is None:
        raise GeoPackageError(f"{where}: invalid envelope flag")
    wkb = blob[8 + envelope_bytes :]
    _check_wkb(wkb, where)
    return wkb


def _check_wkb(wkb: bytes, where: str) -> None:
    if len(wkb) < 5 or wkb[0] not in (0, 1):
        raise GeoPackageError(f"{where}: invalid WKB")
    kind = struct.unpack("<I" if wkb[0] == 1 else ">I", wkb[1:5])[0]
    if kind not in _WKB_NAMES:
        raise GeoPackageError(f"{where}: unsupported WKB geometry type {kind} (2D only)")


# --- Writer ------------------------------------------------------------------------------------


def write_geopackage(
    path: Path,
    srs: Sequence[Srs],
    layers: Iterable[
        tuple[
            str,
            str,
            int,
            str,
            Sequence[tuple[str, str]],
            Iterable[tuple[Mapping[str, Any] | tuple[bytes, Sequence[float]], Sequence[Any]]],
        ]
    ],
    last_change: str,
    *,
    reproducible: bool = False,
) -> None:
    """Write a GeoPackage with feature tables (replaces ``path``).

    Args:
        path: Output file.
        srs: CRS rows besides the two undefined ones required by the standard.
        layers: ``(name, geometry type, srs id, description, columns, rows)``; each row is
            ``(geometry, values)`` where ``geometry`` is a GeoJSON-like dict or an already
            encoded ``(blob, envelope)``, and ``values`` follow ``columns``.
        last_change: ISO timestamp written to ``gpkg_contents`` (fixed for reproducibility).
        reproducible: Fix the SQLite library version in the file header (see module docstring).
    """
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        db.execute(f"PRAGMA user_version = {USER_VERSION}")
        db.executescript(_SCHEMA_SQL)
        db.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
            [
                *_UNDEFINED_SRS,
                *(
                    (
                        s.name,
                        s.srs_id,
                        s.organization,
                        s.organization_coordsys_id,
                        s.definition,
                        None,
                    )
                    for s in srs
                ),
            ],
        )
        for name, geometry_type, srs_id, description, columns, rows in layers:
            _add_layer(db, name, geometry_type, srs_id, columns, rows, description, last_change)
        db.commit()
        db.execute("VACUUM")
    finally:
        db.close()
    if reproducible:
        with path.open("r+b") as handle:
            handle.seek(96)
            handle.write(struct.pack(">I", _FIXED_SQLITE_VERSION))


def _add_layer(
    db: sqlite3.Connection,
    name: str,
    geometry_type: str,
    srs_id: int,
    columns: Sequence[tuple[str, str]],
    rows: Iterable[tuple[Mapping[str, Any] | tuple[bytes, Sequence[float]], Sequence[Any]]],
    description: str,
    last_change: str,
) -> None:
    cols_sql = ", ".join(f"{c} {t}" for c, t in columns)
    db.execute(
        f"CREATE TABLE {name} (fid INTEGER PRIMARY KEY AUTOINCREMENT, "
        f"geom {geometry_type}{', ' if cols_sql else ''}{cols_sql})"
    )
    envs = []
    placeholders = ", ".join("?" for _ in range(len(columns) + 1))
    names = ", ".join(["geom", *(c for c, _ in columns)])
    for geometry, values in rows:
        if isinstance(geometry, tuple):
            blob, env = geometry
        else:
            blob, env = encode_geometry(geometry, srs_id)
        envs.append(env)
        db.execute(f"INSERT INTO {name} ({names}) VALUES ({placeholders})", (blob, *values))
    db.execute(
        "INSERT INTO gpkg_contents VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            name,
            description,
            last_change,
            min((e[0] for e in envs), default=None),
            min((e[2] for e in envs), default=None),
            max((e[1] for e in envs), default=None),
            max((e[3] for e in envs), default=None),
            srs_id,
        ),
    )
    db.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
        (name, geometry_type, srs_id),
    )


# --- Reader ------------------------------------------------------------------------------------


def _value(declared: str, value: object, where: str) -> str | int | float | bool | None:
    if value is None:
        return None
    kind = declared.upper().split("(")[0].strip()
    if kind == "BOOLEAN":
        if value not in (0, 1):
            raise GeoPackageError(f"{where}: BOOLEAN value must be 0 or 1, got {value!r}")
        return bool(value)
    if kind in ("INTEGER", "INT", "MEDIUMINT", "SMALLINT", "TINYINT", "REAL", "DOUBLE", "FLOAT"):
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise GeoPackageError(f"{where}: {kind} column holds {type(value).__name__} {value!r}")
        return int(value) if kind not in ("REAL", "DOUBLE", "FLOAT") else float(value)
    return str(value)


def read_geopackage(path: Path) -> dict[str, Layer]:
    """Read every feature table of a GeoPackage (read-only; untrusted files are safe to open).

    Raises:
        GeoPackageError: If the file is not a valid GeoPackage, or uses unsupported features.
    """
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error as exc:  # pragma: no cover - sqlite opens lazily
        raise GeoPackageError(f"cannot open GeoPackage: {exc}") from None
    try:
        db.execute("PRAGMA trusted_schema = OFF")
        try:
            check = db.execute("PRAGMA quick_check").fetchone()[0]
            app_id = db.execute("PRAGMA application_id").fetchone()[0]
        except sqlite3.DatabaseError:
            raise GeoPackageError("the file is not an SQLite database (GeoPackage)") from None
        if check != "ok":
            raise GeoPackageError(f"the GeoPackage is damaged: {check}")
        if app_id != APPLICATION_ID:
            raise GeoPackageError("the file is an SQLite database but not a GeoPackage")
        try:
            srs_rows = db.execute(
                "SELECT srs_name, srs_id, organization, organization_coordsys_id, definition "
                "FROM gpkg_spatial_ref_sys"
            ).fetchall()
            contents = db.execute(
                "SELECT c.table_name, g.column_name, g.geometry_type_name, g.srs_id, g.z, g.m "
                "FROM gpkg_contents c JOIN gpkg_geometry_columns g ON g.table_name = c.table_name "
                "WHERE c.data_type = 'features' ORDER BY c.table_name"
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise GeoPackageError(f"missing GeoPackage metadata tables: {exc}") from None
        srs = {r[1]: Srs(r[0], r[1], r[2], r[3], r[4]) for r in srs_rows}
        layers: dict[str, Layer] = {}
        for table, geom_col, geom_type, srs_id, z, m in contents:
            where = f"layers.gpkg/{table}"
            if geom_col != "geom":
                raise GeoPackageError(f"{where}: the geometry column must be named geom")
            if z or m:
                raise GeoPackageError(f"{where}: Z and M coordinates are not supported (2D only)")
            if str(geom_type).upper() not in GEOMETRY_TYPES:
                raise GeoPackageError(f"{where}: unsupported geometry type {geom_type}")
            if srs_id not in srs:
                raise GeoPackageError(f"{where}: SRS {srs_id} is not declared")
            info = db.execute(f"PRAGMA table_info('{table}')").fetchall()
            columns = tuple((c[1], str(c[2])) for c in info if c[1] not in ("fid", "geom"))
            names = ", ".join(f'"{c}"' for c, _ in columns)
            query = f'SELECT geom{", " if names else ""}{names} FROM "{table}" ORDER BY fid'
            rows = []
            for n, record in enumerate(db.execute(query), start=1):
                blob = record[0]
                wkb = None if blob is None else _blob_to_wkb(bytes(blob), f"{where} row {n}")
                attrs = {
                    col: _value(declared, value, f"{where} row {n} {col}")
                    for (col, declared), value in zip(columns, record[1:], strict=True)
                }
                rows.append((attrs, wkb))
            layers[table] = Layer(
                str(table), str(geom_type).upper(), srs[srs_id], columns, tuple(rows)
            )
        return layers
    finally:
        db.close()

"""Raw source registry (Spec 00 §3 Onboarding: "national raw sources as versioned files").

Registering a source **processes nothing**: the file is copied into the hub storage directory
while its SHA-256 is computed (streamed in 1 MiB chunks, never loaded whole), and only its
structure is checked: a GeoPackage's tables and columns (without reading rows) or a CSV's header
row. Processing happens later, per onboarded municipality (:mod:`.base`).

Expected structure per layer type (docs/data-processing/DP-003):

* ``boundaries``: GeoPackage, a polygon table with ``municipality_code`` and ``name``;
* ``spatial_units``: GeoPackage, a polygon table with ``unit_code``, ``name`` and
  ``municipality_code`` (any unit: communities, census blocks, grid cells; the choice of unit is
  data, see ADR 0013);
* ``network``: GeoPackage with a point table with ``node_code`` and a line table with
  ``edge_code``, ``from_node``, ``to_node``, ``length_m``, ``travel_time_walk_min``,
  ``travel_time_car_min`` (and optionally ``closable``);
* ``population``: CSV ``unit_code``, ``group_id``, ``population``;
* ``groups``: CSV ``group_id``, ``name``, ``definition_rule``;
* ``services``: CSV ``service_id``, ``name``, ``service_unit``, ``max_acceptable_wait``;
* ``dem``, ``transit``, ``other``: registered and checksummed only (not processed in v0.2).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.gpkg import GeoPackageError, LayerInfo, layer_info
from solidaritynode_backend.services.hub.common import QUALITY, HubError, jsonb

__all__ = [
    "LAYER_TYPES",
    "PROCESSED_TYPES",
    "SourceMeta",
    "find_table",
    "latest_sources",
    "list_sources",
    "register_from_metadata",
    "register_source",
    "source_path",
]

LAYER_TYPES = (
    "boundaries",
    "spatial_units",
    "network",
    "population",
    "dem",
    "transit",
    "groups",
    "services",
    "other",
)
PROCESSED_TYPES = ("boundaries", "spatial_units", "network", "population", "groups", "services")
"""Layer types the base step reads (the latest registered version of each)."""

GPKG_TABLES: dict[str, tuple[tuple[str, ...], ...]] = {
    "boundaries": (("municipality_code", "name"),),
    "spatial_units": (("unit_code", "name", "municipality_code"),),
    "network": (
        ("node_code",),
        (
            "edge_code",
            "from_node",
            "to_node",
            "length_m",
            "travel_time_walk_min",
            "travel_time_car_min",
        ),
    ),
}
CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "population": ("unit_code", "group_id", "population"),
    "groups": ("group_id", "name", "definition_rule"),
    "services": ("service_id", "name", "service_unit", "max_acceptable_wait"),
}
CHUNK = 1024 * 1024
_NOTE = re.compile(r"^DP-\d{3}$")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class SourceMeta:
    """What a person states when registering a source."""

    name: str
    layer_type: str
    coverage: str
    version: str
    licence: str
    attribution: str
    processing_note: str
    quality: str = "open_data"
    synthetic: bool = False

    def check(self) -> None:
        """Refuse missing or unknown values.

        Raises:
            HubError: Naming the first problem.
        """
        for field in ("name", "coverage", "version", "licence", "attribution"):
            if not str(getattr(self, field)).strip():
                raise HubError("hub.source.field_required", field=field)
        if self.layer_type not in LAYER_TYPES:
            raise HubError(
                "hub.source.unknown_layer_type",
                layer_type=self.layer_type,
                allowed=", ".join(LAYER_TYPES),
            )
        if not _NOTE.match(self.processing_note):
            raise HubError("hub.source.bad_note", note=self.processing_note)
        if self.quality not in QUALITY:
            raise HubError("hub.source.bad_quality", quality=self.quality)


def find_table(
    tables: dict[str, LayerInfo], columns: Iterable[str], kinds: Iterable[str]
) -> LayerInfo | None:
    """Return the first table of geometry type in ``kinds`` that has all ``columns``."""
    wanted, types = set(columns), set(kinds)
    for info in tables.values():
        names = {c for c, _ in info.columns}
        if wanted <= names and (info.geometry_type in types or "GEOMETRY" in types):
            return info
    return None


_GEOMETRY_KINDS = {
    "boundaries": ("POLYGON", "MULTIPOLYGON"),
    "spatial_units": ("POLYGON", "MULTIPOLYGON"),
}


def _inspect(layer_type: str, path: Path, file_name: str) -> dict[str, Any]:
    """Check the structure of a source without reading its rows; return what was found."""
    if layer_type in GPKG_TABLES:
        try:
            tables = layer_info(path)
        except GeoPackageError as exc:
            raise HubError("hub.source.not_gpkg", file=file_name, detail=str(exc)) from None
        found: dict[str, Any] = {"format": "gpkg", "tables": {}}
        for i, columns in enumerate(GPKG_TABLES[layer_type]):
            if layer_type == "network":
                kinds = ("POINT",) if i == 0 else ("LINESTRING", "MULTILINESTRING")
            else:
                kinds = _GEOMETRY_KINDS[layer_type]
            info = find_table(tables, columns, kinds)
            if info is None:
                raise HubError(
                    "hub.source.missing_table",
                    file=file_name,
                    kinds="/".join(kinds),
                    columns=", ".join(columns),
                )
            found["tables"][info.name] = {
                "geometry_type": info.geometry_type,
                "crs": f"{info.srs.organization.upper()}:{info.srs.organization_coordsys_id}",
                "rows": info.rows,
                "columns": [c for c, _ in info.columns],
            }
        return found
    if layer_type in CSV_HEADERS:
        with path.open("rb") as handle:
            first = handle.readline(64 * 1024)
        try:
            header = first.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            raise HubError("hub.source.not_utf8", file=file_name) from None
        found_columns = [c.strip() for c in header.split(",")]
        if missing := [c for c in CSV_HEADERS[layer_type] if c not in found_columns]:
            raise HubError(
                "hub.source.missing_columns",
                file=file_name,
                columns=", ".join(missing),
            )
        return {"format": "csv", "columns": found_columns}
    return {"format": Path(file_name).suffix.lstrip(".").lower() or "unknown"}


def _copy_hashing(stream: BinaryIO | Iterator[bytes], target: Path, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    if isinstance(stream, Iterator):
        chunks: Iterable[bytes] = stream
    else:
        reader = stream
        chunks = iter(lambda: reader.read(CHUNK), b"")
    with target.open("wb") as out:
        for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise HubError("hub.source.too_large", status=413, limit=limit // (1024 * 1024))
            digest.update(chunk)
            out.write(chunk)
    if size == 0:
        raise HubError("hub.source.empty")
    return digest.hexdigest(), size


def register_source(
    db: Session,
    settings: Settings,
    stream: BinaryIO | Iterator[bytes],
    file_name: str,
    meta: SourceMeta,
    user_id: int | None,
) -> tuple[dict[str, Any], bool]:
    """Register a raw source file (nothing is processed).

    The file is streamed into ``<hub_storage_dir>/sources/<id>-<sha>/`` while its SHA-256 is
    computed, then its structure is checked (tables and columns or the CSV header).

    Returns:
        The source row and whether it was newly registered (``False``: the same name, version
        and content were already registered, nothing changed).

    Raises:
        HubError: On a missing or invalid field, an empty or too large file, a structure that
            does not match the layer type, or the same name and version with other content.
    """
    meta.check()
    safe = _SAFE_NAME.sub("_", Path(file_name).name).strip("._") or "source"
    staging = settings.hub_storage_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    limit = int(settings.hub_max_source_mb * 1024 * 1024)
    with tempfile.NamedTemporaryFile(dir=staging, delete=False, suffix=f"-{safe}") as tmp:
        tmp_path = Path(tmp.name)
    try:
        sha, size = _copy_hashing(stream, tmp_path, limit)
        existing = db.execute(
            text("SELECT id, sha256 FROM hub_sources WHERE name = :n AND version = :v"),
            {"n": meta.name, "v": meta.version},
        ).one_or_none()
        if existing is not None:
            if existing.sha256 != sha:
                raise HubError(
                    "hub.source.version_conflict", status=409, name=meta.name, version=meta.version
                )
            return get_source(db, int(existing.id)), False
        details = _inspect(meta.layer_type, tmp_path, safe)
        source_id = int(
            db.execute(
                text(
                    "INSERT INTO hub_sources (name, layer_type, coverage, version, licence, "
                    "attribution, processing_note, quality, synthetic, file_name, path, sha256, "
                    "bytes, "
                    "details, registered_by) VALUES (:n, :t, :c, :v, :l, :a, :p, :q, :syn, :f, '', "
                    ":s, :b, CAST(:d AS jsonb), :u) RETURNING id"
                ),
                {
                    "n": meta.name,
                    "t": meta.layer_type,
                    "c": meta.coverage,
                    "v": meta.version,
                    "l": meta.licence,
                    "a": meta.attribution,
                    "p": meta.processing_note,
                    "q": meta.quality,
                    "syn": meta.synthetic,
                    "f": safe,
                    "s": sha,
                    "b": size,
                    "d": jsonb(details),
                    "u": user_id,
                },
            ).scalar_one()
        )
        relative = Path("sources") / f"{source_id:05d}-{sha[:12]}" / safe
        target = settings.hub_storage_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, target)
        db.execute(
            text("UPDATE hub_sources SET path = :p WHERE id = :id"),
            {"p": relative.as_posix(), "id": source_id},
        )
        return get_source(db, source_id), True
    finally:
        tmp_path.unlink(missing_ok=True)


_COLUMNS = (
    "id, name, layer_type, coverage, version, licence, attribution, processing_note, quality, "
    "synthetic, "
    "file_name, path, sha256, bytes, details, registered_at, registered_by"
)


def get_source(db: Session, source_id: int) -> dict[str, Any]:
    """Return one source row as a dict.

    Raises:
        HubError: If it does not exist.
    """
    row = (
        db.execute(text(f"SELECT {_COLUMNS} FROM hub_sources WHERE id = :id"), {"id": source_id})
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("hub.error.source_not_found", status=404, id=source_id)
    return dict(row)


def list_sources(db: Session) -> list[dict[str, Any]]:
    """Return every registered source, newest first."""
    return [
        dict(r)
        for r in db.execute(
            text(f"SELECT {_COLUMNS} FROM hub_sources ORDER BY registered_at DESC, id DESC")
        ).mappings()
    ]


def latest_sources(db: Session) -> dict[str, dict[str, Any]]:
    """Return the most recently registered source of each layer type."""
    out: dict[str, dict[str, Any]] = {}
    for row in db.execute(
        text(
            f"SELECT DISTINCT ON (layer_type) {_COLUMNS} FROM hub_sources "
            "ORDER BY layer_type, registered_at DESC, id DESC"
        )
    ).mappings():
        out[str(row["layer_type"])] = dict(row)
    return out


def source_path(settings: Settings, source: Mapping[str, Any]) -> Path:
    """Return the stored file of a source."""
    return settings.hub_storage_dir / str(source["path"])


def source_input(source: Mapping[str, Any]) -> dict[str, Any]:
    """Return how a processing record cites a source (name, version, checksum, licence)."""
    return {
        "source_id": source["id"],
        "name": source["name"],
        "layer_type": source["layer_type"],
        "version": source["version"],
        "sha256": source["sha256"],
        "licence": source["licence"],
        "attribution": source["attribution"],
        "processing_note": source["processing_note"],
    }


def register_from_metadata(
    db: Session, settings: Settings, directory: Path, user_id: int | None
) -> list[tuple[dict[str, Any], bool]]:
    """Register every file listed in ``<directory>/sources.json`` (demo and scripted setups).

    Each entry has ``file`` plus the :class:`SourceMeta` fields. Already registered files (same
    name, version and content) are left as they are.
    """
    entries = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    out = []
    for entry in entries:
        meta = SourceMeta(
            name=entry["name"],
            layer_type=entry["layer_type"],
            coverage=entry["coverage"],
            version=entry["version"],
            licence=entry["licence"],
            attribution=entry["attribution"],
            processing_note=entry["processing_note"],
            quality=entry.get("quality", "open_data"),
            synthetic=bool(entry.get("synthetic", False)),
        )
        with (directory / entry["file"]).open("rb") as handle:
            out.append(register_source(db, settings, handle, entry["file"], meta, user_id))
    return out

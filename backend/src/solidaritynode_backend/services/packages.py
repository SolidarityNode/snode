"""Data package validation, preview of changes and import (ADR 0013, accepted for v0.1).

A package is a directory or a ``.zip``/``.tar``/``.tar.gz`` archive with a ``manifest.json``
and GeoJSON layers and CSV tables listed with SHA-256 checksums. Import is two-step: a
**preview** of the changes against the active data version (features added, changed, closed per
layer, plus coverage changes), then the **import** after confirmation, in one transaction. The
imported version becomes active; older versions stay, and runs keep pointing to theirs.

Rules: re-importing the same version with the same content is a no-op; the same version with
different content, an incompatible schema version, a bad checksum, or a feature that disappears
(features are closed with ``valid_to``, never deleted) is refused with a clear message.
On import the baseline scenario gets a version for the new data and a baseline run is queued.
Edge-effect warnings (OQ-28, warning only): core units touching a buffer municipality whose
facility layer is ``missing``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tarfile
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.orm import DataVersion, Scenario, ScenarioVersion
from solidaritynode_backend.schemas.scenario import SCENARIO_SCHEMA_VERSION, ScenarioBody
from solidaritynode_backend.services.runs import create_run, reference_problems

__all__ = [
    "COVERAGE_LAYERS",
    "FEATURE_LAYERS",
    "SUPPORTED_SCHEMA_MAJOR",
    "ImportOutcome",
    "IncompatibleSchemaError",
    "PackageContent",
    "PackageError",
    "import_package",
    "opened_package",
    "preview_package",
    "read_package",
]

SUPPORTED_SCHEMA_MAJOR = 1
FORMAT = "solidaritynode-data-package"
FEATURE_LAYERS: dict[str, str] = {
    "municipalities": "municipality_id",
    "spatial_units": "unit_id",
    "facilities": "facility_id",
    "network_nodes": "node_id",
    "network_edges": "edge_id",
}
REQUIRED_LAYERS = ("municipalities", "spatial_units", "network_nodes", "network_edges")
TABLE_FILES = {
    "groups": "tables/groups.csv",
    "services": "tables/services.csv",
    "population": "tables/population.csv",
    "facility_services": "tables/facility_services.csv",
    "hand_checks": "checks/hand_check_travel_times.csv",
}
REQUIRED_TABLES = ("groups", "services", "population")
COVERAGE_LAYERS = ("boundaries", "population", "network", "facilities", "transit")
COVERAGE_STATUS = frozenset({"missing", "open_data", "estimated", "verified"})
QUALITY = frozenset({"open_data", "estimated", "verified_by_municipality"})
META_KEYS = ("municipality_id", "role", "quality", "valid_from", "valid_to", "processing_note")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SCHEMA = re.compile(r"^(\d+)\.(\d+)$")
_CRS = re.compile(r"^EPSG:(\d{4,6})$")
_GEOM_HASH = "_geometry_sha256"


class PackageError(ValueError):
    """The package is invalid or cannot be imported."""


class IncompatibleSchemaError(PackageError):
    """The package's schema version is not supported by this installation."""


@dataclass
class PackageContent:
    """A validated package, ready to preview or import."""

    manifest: dict[str, Any]
    manifest_sha256: str
    srid: int
    features: dict[str, dict[str, tuple[dict[str, Any], dict[str, Any]]]]
    records: dict[str, list[dict[str, Any]]]
    coverage: list[tuple[str, str, str, str]]
    warnings: list[str] = field(default_factory=list)

    @property
    def package_id(self) -> str:
        """Return the package id."""
        return str(self.manifest["package_id"])

    @property
    def version(self) -> str:
        """Return the package version."""
        return str(self.manifest["version"])


# --- Reading and validating --------------------------------------------------------------------


def _safe_members(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise PackageError(f"unsafe path in archive: {name}")


def _package_root(directory: Path) -> Path:
    if (directory / "manifest.json").is_file():
        return directory
    candidates = [p for p in directory.iterdir() if (p / "manifest.json").is_file()]
    if len(candidates) == 1:
        return candidates[0]
    raise PackageError("manifest.json not found in the package")


@contextmanager
def opened_package(source: Path) -> Iterator[Path]:
    """Yield the package directory of ``source`` (a directory or an archive).

    Archives are extracted to a temporary directory, rejecting absolute paths, ``..`` and links.
    """
    if source.is_dir():
        yield _package_root(source)
        return
    if not source.is_file():
        raise PackageError(f"package not found: {source}")
    with tempfile.TemporaryDirectory(prefix="sn-package-") as tmp:
        target = Path(tmp)
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as archive:
                _safe_members(archive.namelist())
                archive.extractall(target)
        elif tarfile.is_tarfile(source):
            with tarfile.open(source) as archive:
                _safe_members(archive.getnames())
                if any(not (m.isfile() or m.isdir()) for m in archive.getmembers()):
                    raise PackageError("archive contains links or special files")
                archive.extractall(target, filter="data")
        else:
            raise PackageError("not a directory, .zip or .tar archive")
        yield _package_root(target)


def _check_manifest(m: dict[str, Any]) -> int:
    if m.get("format") != FORMAT:
        raise PackageError(f"manifest format must be {FORMAT!r}")
    schema = str(m.get("schema_version", ""))
    match = _SCHEMA.match(schema)
    if not match:
        raise PackageError(f"invalid schema_version {schema!r} (expected MAJOR.MINOR)")
    if int(match.group(1)) != SUPPORTED_SCHEMA_MAJOR:
        raise IncompatibleSchemaError(
            f"package schema version {schema} is not supported: this installation reads "
            f"schema {SUPPORTED_SCHEMA_MAJOR}.x. Update SolidarityNode, or ask the hub for a "
            f"package in schema {SUPPORTED_SCHEMA_MAJOR}.x."
        )
    for key in ("package_id", "version", "created", "crs", "study_area", "coverage", "files"):
        if key not in m:
            raise PackageError(f"manifest: missing {key!r}")
    if not _SEMVER.match(str(m["version"])):
        raise PackageError(
            f"manifest: version {m['version']!r} is not semantic (MAJOR.MINOR.PATCH)"
        )
    try:
        date.fromisoformat(str(m["created"]))
    except ValueError:
        raise PackageError("manifest: created must be a date (YYYY-MM-DD)") from None
    crs = _CRS.match(str(m["crs"]))
    if not crs:
        raise PackageError("manifest: crs must look like EPSG:2100")
    area = m["study_area"]
    if not area.get("core_municipalities"):
        raise PackageError("manifest: study_area needs at least one core municipality")
    if not m.get("processing_notes"):
        raise PackageError("manifest: processing_notes (DP-NNN) are required")
    if not any(c.get("version") == m["version"] for c in m.get("changelog", [])):
        raise PackageError(f"manifest: changelog has no entry for version {m['version']}")
    for mun in [*area["core_municipalities"], *area.get("buffer_municipalities", [])]:
        layers = m["coverage"].get(mun)
        if layers is None:
            raise PackageError(f"manifest: no coverage for municipality {mun}")
        for layer in COVERAGE_LAYERS:
            entry = layers.get(layer)
            if not entry or entry.get("status") not in COVERAGE_STATUS:
                raise PackageError(f"manifest: coverage {mun}/{layer} needs a valid status")
    return int(crs.group(1))


def _check_files(directory: Path, m: dict[str, Any]) -> None:
    listed = set()
    for entry in m["files"]:
        rel = str(entry["path"])
        _safe_members([rel])
        listed.add(rel)
        path = directory / rel
        if not path.is_file():
            raise PackageError(f"file listed in manifest is missing: {rel}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            raise PackageError(f"checksum mismatch for {rel}: the file is damaged or was changed")
    on_disk = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if extra := sorted(on_disk - listed):
        raise PackageError(f"files not listed in the manifest: {', '.join(extra)}")


def _csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _geom_hash(geometry: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()


def read_package(directory: Path) -> PackageContent:
    """Validate a package directory and return its content.

    Raises:
        IncompatibleSchemaError: On an unsupported schema version.
        PackageError: On any other problem (named in the message).
    """
    raw = (directory / "manifest.json").read_bytes()
    try:
        manifest: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PackageError(f"manifest.json is not valid JSON: {exc}") from None
    srid = _check_manifest(manifest)
    _check_files(directory, manifest)
    listed = {str(e["path"]) for e in manifest["files"]}
    area = manifest["study_area"]
    municipalities = {*area["core_municipalities"], *area.get("buffer_municipalities", [])}

    features: dict[str, dict[str, tuple[dict[str, Any], dict[str, Any]]]] = {}
    for layer, key in FEATURE_LAYERS.items():
        rel = f"layers/{layer}.geojson"
        if rel not in listed:
            if layer in REQUIRED_LAYERS:
                raise PackageError(f"required layer missing: {rel}")
            features[layer] = {}
            continue
        data = json.loads((directory / rel).read_text("utf-8"))
        out: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for feature in data.get("features", []):
            props = dict(feature.get("properties") or {})
            fid = str(props.get(key, ""))
            if not fid:
                raise PackageError(f"{layer}: feature without {key}")
            if fid in out:
                raise PackageError(f"{layer}: duplicate id {fid}")
            if feature.get("geometry") is None:
                raise PackageError(f"{layer}/{fid}: missing geometry")
            for meta in META_KEYS:
                if meta not in props:
                    raise PackageError(f"{layer}/{fid}: missing {meta}")
            if props["role"] not in ("core", "buffer"):
                raise PackageError(f"{layer}/{fid}: role must be core or buffer")
            if props["quality"] not in QUALITY:
                raise PackageError(f"{layer}/{fid}: unknown quality {props['quality']!r}")
            if props["municipality_id"] not in municipalities:
                raise PackageError(f"{layer}/{fid}: municipality not in the study area")
            for d in ("valid_from", "valid_to"):
                if props[d] is not None:
                    try:
                        date.fromisoformat(str(props[d]))
                    except ValueError:
                        raise PackageError(f"{layer}/{fid}: {d} is not a date") from None
            props[_GEOM_HASH] = _geom_hash(feature["geometry"])
            out[fid] = (props, feature["geometry"])
        features[layer] = out

    tables: dict[str, list[dict[str, Any]]] = {}
    for table, rel in TABLE_FILES.items():
        if rel in listed:
            tables[table] = _csv(directory / rel)
        elif table in REQUIRED_TABLES:
            raise PackageError(f"required table missing: {rel}")
        else:
            tables[table] = []

    nodes = features["network_nodes"]
    units = features["spatial_units"]
    for uid, (props, _) in units.items():
        if props.get("centroid_node_id") not in nodes:
            raise PackageError(f"spatial_units/{uid}: centroid node not in the network")
        props["population"] = {}
    for row in tables.pop("population"):
        if row["unit_id"] not in units:
            raise PackageError(f"population: unknown unit {row['unit_id']}")
        units[row["unit_id"]][0]["population"][row["group_id"]] = int(row["population"])
    facilities = features["facilities"]
    for fid, (props, _) in facilities.items():
        if props.get("node_id") not in nodes:
            raise PackageError(f"facilities/{fid}: node {props.get('node_id')} not in the network")
        if props.get("unit_id") not in units:
            raise PackageError(f"facilities/{fid}: unit {props.get('unit_id')} unknown")
        props["services"] = {}
    for row in tables.pop("facility_services"):
        if row["facility_id"] not in facilities:
            raise PackageError(f"facility_services: unknown facility {row['facility_id']}")
        facilities[row["facility_id"]][0]["services"][row["service_id"]] = {
            k: (float(row[k]) if row[k] else None) for k in ("places", "staff", "throughput")
        }
    for eid, (props, _) in features["network_edges"].items():
        for end in ("from_node_id", "to_node_id"):
            if props.get(end) not in nodes:
                raise PackageError(f"network_edges/{eid}: {end} not in the network")

    coverage = [
        (mun, layer, str(entry["status"]), str(entry.get("version", manifest["version"])))
        for mun, layers in sorted(manifest["coverage"].items())
        for layer, entry in sorted(layers.items())
    ]
    return PackageContent(
        manifest=manifest,
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
        srid=srid,
        features=features,
        records=tables,
        coverage=coverage,
    )


# --- Preview -----------------------------------------------------------------------------------


def _active(db: Session) -> DataVersion | None:
    return db.scalar(select(DataVersion).where(DataVersion.active))


def _semver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _diff_fields(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    keys = sorted(set(old) | set(new))
    out = []
    for k in keys:
        if old.get(k) != new.get(k):
            out.append("geometry" if k == _GEOM_HASH else k)
    return out


def preview_package(db: Session, content: PackageContent) -> dict[str, Any]:
    """Compare a package with the active data version (nothing is written).

    Returns:
        ``status`` (``new``, ``update``, ``same_version``, ``conflict``, ``other_package``),
        per-layer ``added``/``changed``/``closed``/``removed`` feature ids, coverage changes,
        blocking ``problems`` and ``warnings``.
    """
    active = _active(db)
    existing = db.scalar(
        select(DataVersion).where(
            DataVersion.package_id == content.package_id, DataVersion.version == content.version
        )
    )
    problems: list[str] = []
    warnings = list(content.warnings)
    if existing is not None:
        status = (
            "same_version" if existing.manifest_sha256 == content.manifest_sha256 else "conflict"
        )
        if status == "conflict":
            problems.append(
                f"version {content.version} of {content.package_id} was already imported with "
                "different content; the hub must publish a new version number"
            )
    elif active is None:
        status = "new"
    elif active.package_id != content.package_id:
        status = "other_package"
        warnings.append(
            f"this package ({content.package_id}) is for a different study area than the active "
            f"data ({active.package_id})"
        )
    else:
        status = "update"
        if _semver(content.version) <= _semver(active.version):
            warnings.append(
                f"version {content.version} is not newer than the active {active.version}"
            )

    old: dict[str, dict[str, dict[str, Any]]] = {layer: {} for layer in FEATURE_LAYERS}
    old_coverage: dict[tuple[str, str], str] = {}
    if active is not None:
        for layer, fid, props in db.execute(
            text(
                "SELECT layer, feature_id, properties FROM data_features "
                "WHERE data_version_id = :dv"
            ),
            {"dv": active.id},
        ):
            old.setdefault(layer, {})[fid] = props
        for mun, layer, cov in db.execute(
            text(
                "SELECT municipality_id, layer, status FROM data_coverage "
                "WHERE data_version_id = :dv"
            ),
            {"dv": active.id},
        ):
            old_coverage[(mun, layer)] = cov

    layers: dict[str, dict[str, Any]] = {}
    for layer in FEATURE_LAYERS:
        new = {fid: props for fid, (props, _) in content.features[layer].items()}
        before = old.get(layer, {})
        added = sorted(set(new) - set(before))
        removed = sorted(set(before) - set(new))
        closed, changed = [], []
        for fid in sorted(set(new) & set(before)):
            fields = _diff_fields(before[fid], new[fid])
            if before[fid].get("valid_to") is None and new[fid].get("valid_to") is not None:
                closed.append(fid)
                fields = [f for f in fields if f != "valid_to"]
            if fields:
                changed.append({"id": fid, "fields": fields})
        if removed and status == "update":
            problems.append(
                f"{layer}: features {', '.join(removed)} disappeared; packages must close "
                "features (valid_to), never delete them"
            )
        layers[layer] = {
            "added": added,
            "changed": changed,
            "closed": closed,
            "removed": removed,
            "unchanged": len(set(new) & set(before) - {c["id"] for c in changed} - set(closed)),
            "total": len(new),
        }
    coverage_changes = [
        {
            "municipality_id": mun,
            "layer": layer,
            "before": old_coverage.get((mun, layer)),
            "after": s,
        }
        for mun, layer, s, _ in content.coverage
        if old_coverage.get((mun, layer)) != s
    ]
    return {
        "package_id": content.package_id,
        "version": content.version,
        "schema_version": content.manifest["schema_version"],
        "created": content.manifest["created"],
        "synthetic": bool(content.manifest.get("synthetic", False)),
        "changelog": content.manifest.get("changelog", []),
        "active": {"package_id": active.package_id, "version": active.version} if active else None,
        "status": status,
        "layers": layers,
        "coverage_changes": coverage_changes if active is not None else [],
        "problems": problems,
        "warnings": warnings,
    }


# --- Import ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportOutcome:
    """Result of :func:`import_package`."""

    data_version_id: int
    noop: bool
    preview: dict[str, Any]
    baseline_run_id: str | None
    revalidation: list[dict[str, Any]]


BASELINE_NAME = "Baseline (no changes)"


def _baseline(
    db: Session, dv: DataVersion, user_id: int | None
) -> tuple[Scenario, ScenarioVersion]:
    scenario = db.scalar(select(Scenario).where(Scenario.is_baseline))
    if scenario is None:
        scenario = Scenario(
            id=uuid.uuid4(), owner_id=None, visibility="shared", is_baseline=True, latest_version=0
        )
        db.add(scenario)
        db.flush()
    scenario.latest_version += 1
    scenario.updated_at = datetime.now(UTC)
    version = ScenarioVersion(
        scenario_id=scenario.id,
        version=scenario.latest_version,
        name=BASELINE_NAME,
        description=f"Empty overlay on data {dv.package_id} {dv.version}.",
        schema_version=SCENARIO_SCHEMA_VERSION,
        body=ScenarioBody().model_dump(),
        data_version_id=dv.id,
        created_by=user_id,
    )
    db.add(version)
    db.flush()
    return scenario, version


def revalidate_scenarios(db: Session, data_version_id: int) -> list[dict[str, Any]]:
    """Check the latest version of every scenario against a data version.

    Returns:
        One entry per scenario whose references do not resolve, with the problems.
    """
    report = []
    for scenario, version in db.execute(
        select(Scenario, ScenarioVersion)
        .join(
            ScenarioVersion,
            (ScenarioVersion.scenario_id == Scenario.id)
            & (ScenarioVersion.version == Scenario.latest_version),
        )
        .where(Scenario.deleted_at.is_(None), Scenario.is_baseline.is_(False))
    ):
        problems = reference_problems(
            db, ScenarioBody.model_validate(version.body), data_version_id
        )
        if problems:
            report.append(
                {"scenario_id": str(scenario.id), "name": version.name, "problems": problems}
            )
    return report


def import_package(
    db: Session, settings: Settings, content: PackageContent, user_id: int | None
) -> ImportOutcome:
    """Import a validated package in one transaction and make it the active data version.

    Raises:
        PackageError: If the preview has blocking problems.
    """
    preview = preview_package(db, content)
    if preview["problems"]:
        raise PackageError("; ".join(preview["problems"]))
    if preview["status"] == "same_version":
        existing = db.scalar(
            select(DataVersion).where(
                DataVersion.package_id == content.package_id,
                DataVersion.version == content.version,
            )
        )
        assert existing is not None
        return ImportOutcome(existing.id, True, preview, None, [])

    dv = DataVersion(
        package_id=content.package_id,
        version=content.version,
        schema_version=str(content.manifest["schema_version"]),
        created=date.fromisoformat(str(content.manifest["created"])),
        srid=content.srid,
        manifest=content.manifest,
        manifest_sha256=content.manifest_sha256,
        active=False,
        imported_by=user_id,
    )
    db.add(dv)
    db.flush()
    rows = [
        {
            "dv": dv.id,
            "layer": layer,
            "fid": fid,
            "props": json.dumps(props),
            "geom": json.dumps(geometry),
            "srid": content.srid,
        }
        for layer, items in content.features.items()
        for fid, (props, geometry) in items.items()
    ]
    db.execute(
        text(
            "INSERT INTO data_features (data_version_id, layer, feature_id, properties, geom) "
            "VALUES (:dv, :layer, :fid, CAST(:props AS jsonb), "
            "ST_SetSRID(ST_GeomFromGeoJSON(:geom), :srid))"
        ),
        rows,
    )
    records = [
        {"dv": dv.id, "t": table, "n": n, "props": json.dumps(row)}
        for table, table_rows in content.records.items()
        for n, row in enumerate(table_rows)
    ]
    if records:
        db.execute(
            text(
                "INSERT INTO data_records (data_version_id, table_name, row_no, properties) "
                "VALUES (:dv, :t, :n, CAST(:props AS jsonb))"
            ),
            records,
        )
    db.execute(
        text(
            "INSERT INTO data_coverage (data_version_id, municipality_id, layer, status, "
            "layer_version) VALUES (:dv, :m, :l, :s, :v)"
        ),
        [{"dv": dv.id, "m": m, "l": layer, "s": s, "v": v} for m, layer, s, v in content.coverage],
    )
    db.execute(
        text(
            """
            INSERT INTO data_warnings (data_version_id, unit_id, code, detail)
            SELECT DISTINCT u.data_version_id, u.feature_id, 'edge_effect',
                   'Neighbouring municipality ' || m.feature_id || ' has no facility data '
                   || '(facilities: missing); results near this boundary may be biased (OQ-28).'
            FROM data_features u
            JOIN data_features m
              ON m.data_version_id = u.data_version_id AND m.layer = 'municipalities'
            JOIN data_coverage c
              ON c.data_version_id = u.data_version_id AND c.municipality_id = m.feature_id
             AND c.layer = 'facilities' AND c.status = 'missing'
            WHERE u.data_version_id = :dv AND u.layer = 'spatial_units'
              AND u.properties->>'role' = 'core' AND m.properties->>'role' = 'buffer'
              AND ST_Intersects(u.geom, m.geom)
            """
        ),
        {"dv": dv.id},
    )
    db.execute(update(DataVersion).where(DataVersion.active).values(active=False))
    db.flush()
    dv.active = True
    db.flush()
    scenario, version = _baseline(db, dv, user_id)
    baseline = create_run(db, settings, scenario, version, dv, created_by=user_id)
    revalidation = revalidate_scenarios(db, dv.id)
    return ImportOutcome(dv.id, False, preview, str(baseline.run.id), revalidation)


def stage_upload(settings: Settings, data: bytes) -> str:
    """Store an uploaded archive for a later import; return its staging id."""
    staging_id = uuid.uuid4().hex
    target = settings.results_dir / "staging" / f"{staging_id}.pkg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return staging_id


def staged_path(settings: Settings, staging_id: str) -> Path:
    """Return the path of a staged upload.

    Raises:
        PackageError: If the id is malformed or unknown.
    """
    if not re.fullmatch(r"[0-9a-f]{32}", staging_id):
        raise PackageError("invalid staging id")
    path = settings.results_dir / "staging" / f"{staging_id}.pkg"
    if not path.is_file():
        raise PackageError("staged package not found; upload it again")
    return path


def available_packages(settings: Settings) -> list[dict[str, Any]]:
    """List package directories under ``packages_dir`` (offered on the Admin screen)."""
    out: list[dict[str, Any]] = []
    root = settings.packages_dir
    if not root.is_dir():
        return out
    for path in sorted(root.iterdir()):
        manifest = path / "manifest.json"
        if path.is_dir() and manifest.is_file():
            try:
                m = json.loads(manifest.read_text("utf-8"))
            except json.JSONDecodeError:
                continue
            out.append(
                {
                    "name": path.name,
                    "package_id": m.get("package_id"),
                    "version": m.get("version"),
                    "created": m.get("created"),
                }
            )
    return out


def available_path(settings: Settings, name: str) -> Path:
    """Return the directory of an available package by name.

    Raises:
        PackageError: If the name is not an available package.
    """
    if name not in {p["name"] for p in available_packages(settings)}:
        raise PackageError(f"package {name!r} is not available on this server")
    return settings.packages_dir / name


def archive_directory(directory: Path) -> bytes:
    """Return a zip archive of a package directory (used by tests and the CLI)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(directory).as_posix())
    return buffer.getvalue()

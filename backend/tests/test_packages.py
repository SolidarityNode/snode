"""Data packages: format, checksums, schema version, preview and import (ADR 0013)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text

from solidaritynode_backend.services.packages import (
    IncompatibleSchemaError,
    PackageError,
    archive_directory,
    opened_package,
    read_package,
)
from tests.conftest import PACKAGES, REPO, import_version


def _load_builder():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "build_demo_packages", REPO / "scripts" / "build_demo_packages.py"
    )
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_demo_packages_are_current(tmp_path: Path) -> None:
    _load_builder().build(tmp_path)
    for version in ("1.0.0", "1.1.0"):
        built = sorted(
            p.relative_to(tmp_path / f"demo-{version}")
            for p in (tmp_path / f"demo-{version}").rglob("*")
            if p.is_file()
        )
        committed = PACKAGES / f"demo-{version}"
        for rel in built:
            assert (tmp_path / f"demo-{version}" / rel).read_bytes() == (
                committed / rel
            ).read_bytes(), rel


def test_reads_good_package() -> None:
    content = read_package(PACKAGES / "demo-1.0.0")
    assert content.package_id == "demo-study-area-a"
    assert content.version == "1.0.0"
    assert content.srid == 2100
    assert set(content.features["facilities"]) == {"F1", "F2", "F3"}
    assert len(content.features["spatial_units"]) == 8
    assert content.features["spatial_units"]["A1"][0]["population"]["G-OLD"] == 310
    assert content.features["facilities"]["F1"][0]["services"]["S-HC"]["staff"] == 4


def _copy(tmp_path: Path, version: str = "1.0.0") -> Path:
    target = tmp_path / f"pkg-{version}"
    shutil.copytree(PACKAGES / f"demo-{version}", target)
    return target


def _rechecksum(pkg: Path) -> None:
    manifest = json.loads((pkg / "manifest.json").read_text())
    for entry in manifest["files"]:
        entry["sha256"] = hashlib.sha256((pkg / entry["path"]).read_bytes()).hexdigest()
    (pkg / "manifest.json").write_text(json.dumps(manifest))


def test_bad_checksum_is_refused(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    path = pkg / "tables" / "population.csv"
    path.write_text(path.read_text().replace("310", "311"))
    with pytest.raises(PackageError, match=r"checksum mismatch for tables/population\.csv"):
        read_package(pkg)


def test_unlisted_file_is_refused(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    (pkg / "extra.txt").write_text("x")
    with pytest.raises(PackageError, match="not listed"):
        read_package(pkg)


def test_incompatible_schema_is_refused_with_a_clear_message(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["schema_version"] = "2.0"
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(IncompatibleSchemaError, match=r"schema version 2\.0 is not supported"):
        read_package(pkg)


def test_zip_archive_and_unsafe_paths(tmp_path: Path) -> None:
    archive = tmp_path / "pkg.zip"
    archive.write_bytes(archive_directory(PACKAGES / "demo-1.1.0"))
    with opened_package(archive) as directory:
        assert read_package(directory).version == "1.1.0"
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../manifest.json", "{}")
    with pytest.raises(PackageError, match="unsafe path"), opened_package(evil):
        pass


def test_import_activates_and_reimport_is_noop(as_admin, db) -> None:  # type: ignore[no-untyped-def]
    first = import_version(as_admin, "1.0.0")
    assert first["noop"] is False
    assert first["baseline_run_id"]
    again = import_version(as_admin, "1.0.0")
    assert again["noop"] is True
    assert again["data_version_id"] == first["data_version_id"]
    assert db.scalar(text("SELECT count(*) FROM data_versions")) == 1
    active = as_admin.get("/data-versions/active").json()
    assert (active["version"], active["active"]) == ("1.0.0", True)
    preview = as_admin.post("/packages/preview", json={"name": "demo-1.0.0"}).json()
    assert preview["status"] == "same_version"


def test_preview_lists_exactly_the_expected_changes(as_admin) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    preview = as_admin.post("/packages/preview", json={"name": "demo-1.1.0"}).json()
    assert preview["status"] == "update"
    assert preview["problems"] == []
    layers = preview["layers"]
    assert layers["facilities"]["added"] == ["F4"]
    assert layers["facilities"]["changed"] == [{"id": "F2", "fields": ["services"]}]
    assert layers["facilities"]["closed"] == ["F3"]
    assert layers["facilities"]["unchanged"] == 1
    for layer in ("municipalities", "spatial_units", "network_nodes", "network_edges"):
        diff = layers[layer]
        assert (diff["added"], diff["changed"], diff["closed"], diff["removed"]) == ([], [], [], [])
    assert preview["coverage_changes"] == [
        {"municipality_id": "M-B", "layer": "facilities", "before": "missing", "after": "verified"}
    ]
    # Nothing written by the preview.
    assert as_admin.get("/data-versions/active").json()["version"] == "1.0.0"


def test_upload_preview_and_import(as_admin) -> None:  # type: ignore[no-untyped-def]
    data = archive_directory(PACKAGES / "demo-1.0.0")
    preview = as_admin.post(
        "/packages/upload", content=data, headers={"Content-Type": "application/zip"}
    )
    assert preview.status_code == 200, preview.text
    staging_id = preview.json()["staging_id"]
    assert preview.json()["status"] == "new"
    response = as_admin.post("/packages/import", json={"staging_id": staging_id})
    assert response.status_code == 200
    assert response.json()["noop"] is False


def test_upload_with_bad_checksum_is_refused(as_admin, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    pkg = _copy(tmp_path)
    (pkg / "tables" / "groups.csv").write_text("group_id,name,definition_rule\n")
    response = as_admin.post(
        "/packages/upload",
        content=archive_directory(pkg),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 422
    assert "checksum mismatch" in response.json()["detail"]
    assert as_admin.get("/data-versions").json() == []


def test_same_version_with_other_content_is_refused(as_admin, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    pkg = _copy(tmp_path)
    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["description"] = "changed"
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    buffer = io.BytesIO(archive_directory(pkg))
    response = as_admin.post(
        "/packages/upload", content=buffer.getvalue(), headers={"Content-Type": "application/zip"}
    )
    assert response.json()["status"] == "conflict"
    imported = as_admin.post("/packages/import", json={"staging_id": response.json()["staging_id"]})
    assert imported.status_code == 422
    assert "already imported with different content" in imported.json()["detail"]


def test_deleted_feature_is_refused(as_admin, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    pkg = _copy(tmp_path, "1.1.0")
    layer = pkg / "layers" / "facilities.geojson"
    data = json.loads(layer.read_text())
    data["features"] = [f for f in data["features"] if f["id"] != "F1"]
    layer.write_text(json.dumps(data))
    rows = (pkg / "tables" / "facility_services.csv").read_text().splitlines()
    kept = [r for r in rows if not r.startswith("F1,")]
    (pkg / "tables" / "facility_services.csv").write_text("\n".join(kept) + "\n")
    _rechecksum(pkg)
    response = as_admin.post(
        "/packages/upload",
        content=archive_directory(pkg),
        headers={"Content-Type": "application/zip"},
    )
    assert "never delete them" in " ".join(response.json()["problems"])


def test_edge_effect_warnings_follow_coverage(as_admin) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    assert as_admin.get("/data-versions/active").json()["edge_effect_units"] == ["A3", "A6"]
    import_version(as_admin, "1.1.0")
    assert as_admin.get("/data-versions/active").json()["edge_effect_units"] == []


def test_layers_are_served_in_wgs84_with_metadata(as_admin) -> None:  # type: ignore[no-untyped-def]
    dv = import_version(as_admin, "1.0.0")["data_version_id"]
    units = as_admin.get(f"/data-versions/{dv}/layers/spatial_units").json()
    a3 = next(f for f in units["features"] if f["id"] == "A3")
    assert a3["properties"]["edge_effect_warning"] is True
    assert a3["properties"]["role"] == "core"
    lon, lat = a3["geometry"]["coordinates"][0][0]
    assert 19 < lon < 21
    assert 34 < lat < 36
    b1 = next(f for f in units["features"] if f["id"] == "B1")
    assert (b1["properties"]["role"], b1["properties"]["quality"]) == ("buffer", "estimated")
    assert as_admin.get(f"/data-versions/{dv}/layers/nope").status_code == 404


def test_cli_preview_only_signals_nothing_to_do(as_admin, settings, capsys) -> None:  # type: ignore[no-untyped-def]
    from solidaritynode_backend.cli import NOTHING_TO_DO, import_command

    pkg = str(PACKAGES / "demo-1.0.0")
    assert import_command(settings, pkg, yes=False, preview_only=True) == 0
    assert import_command(settings, pkg, yes=True, preview_only=False) == 0
    assert import_command(settings, pkg, yes=False, preview_only=True) == NOTHING_TO_DO
    assert "already imported: nothing to do" in capsys.readouterr().out

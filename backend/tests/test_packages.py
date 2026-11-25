"""Data packages: format, checksums, schema version, preview and import (ADR 0013)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sqlite3
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
    manifest["schema_version"] = "3.0"
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(
        IncompatibleSchemaError, match=r"schema version 3\.0 is not supported.*schema 2\.x"
    ):
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
        {
            "municipality_id": "M-B",
            "layer": "facilities",
            "before": "missing",
            "after": "verified_by_municipality",
        }
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
    with sqlite3.connect(pkg / "layers.gpkg") as db:
        db.execute("DELETE FROM facilities WHERE facility_id = 'F1'")
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


# --- Schema 2.0: GeoPackage layers, CRS, licences, CSV dialect (ADR 0013) ----------------------


def test_layers_come_from_the_geopackage_in_the_manifest_crs() -> None:
    content = read_package(PACKAGES / "demo-1.1.0")
    props, wkb = content.features["network_edges"]["E01"]
    assert props["closable"] is False
    assert props["length_m"] == 2000.0
    assert wkb[:5] == b"\x01\x02\x00\x00\x00"  # little-endian WKB LineString
    assert content.manifest["layers"]["facilities"]["licence"] == "AGPL-3.0-or-later"
    assert content.manifest["schema_version"] == "2.0"


def test_geojson_package_of_schema_1_is_refused(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["schema_version"] = "1.0"
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(IncompatibleSchemaError, match=r"schema version 1\.0 is not supported"):
        read_package(pkg)


def test_layer_in_another_crs_is_refused(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    with sqlite3.connect(pkg / "layers.gpkg") as db:
        db.execute(
            "INSERT INTO gpkg_spatial_ref_sys VALUES ('WGS 84', 4326, 'EPSG', 4326, 'GEOGCS', NULL)"
        )
        db.execute("UPDATE gpkg_geometry_columns SET srs_id = 4326 WHERE table_name = 'facilities'")
    _rechecksum(pkg)
    with pytest.raises(PackageError, match=r"facilities: geometries are in EPSG:4326.*EPSG:2100"):
        read_package(pkg)


def test_a_file_that_is_not_a_geopackage_is_refused(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    (pkg / "layers.gpkg").write_bytes(b'{"type": "FeatureCollection"}')
    _rechecksum(pkg)
    with pytest.raises(PackageError, match=r"layers\.gpkg: .*not an SQLite database"):
        read_package(pkg)


@pytest.mark.parametrize("missing", ["licence", "attribution"])
def test_every_layer_needs_a_licence_and_attribution(tmp_path: Path, missing: str) -> None:
    pkg = _copy(tmp_path)
    manifest = json.loads((pkg / "manifest.json").read_text())
    del manifest["layers"]["network_edges"][missing]
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(PackageError, match=f"layer network_edges needs a {missing}"):
        read_package(pkg)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "facility_id;service_id;places;staff;throughput\nF1;S-HC;10;4,5;100\n",
            "uses ';' as delimiter",
        ),
        (
            'facility_id,service_id,places,staff,throughput\nF1,S-HC,10,"4,5",100\n',
            r"staff: '4,5' uses a comma as decimal separator; use a dot",
        ),
        (
            "facility_id,service_id,places,staff,throughput\nF1,S-HC,10,4,5,100\n",
            "6 fields, the header has 5. A comma used as decimal separator",
        ),
        (
            "facility_id,service_id,places,staff\nF1,S-HC,10,4\n",
            "header row lacks throughput",
        ),
        ("facility_id,service_id,places,staff,throughput\nF1,S-HC,ten,4,100\n", "not a number"),
    ],
)
def test_csv_dialect_is_enforced(tmp_path: Path, content: str, message: str) -> None:
    pkg = _copy(tmp_path)
    (pkg / "tables" / "facility_services.csv").write_text(content, encoding="utf-8")
    _rechecksum(pkg)
    with pytest.raises(PackageError, match=message):
        read_package(pkg)


def test_csv_in_a_greek_codepage_is_refused_and_a_bom_is_tolerated(tmp_path: Path) -> None:
    pkg = _copy(tmp_path)
    groups = pkg / "tables" / "groups.csv"
    text_ = groups.read_text(encoding="utf-8")
    groups.write_bytes(text_.replace("(synthetic)", "(συνθετικό)").encode("cp1253"))
    _rechecksum(pkg)
    with pytest.raises(PackageError, match=r"not UTF-8.*Windows-1253"):
        read_package(pkg)
    groups.write_bytes(b"\xef\xbb\xbf" + text_.encode("utf-8"))
    _rechecksum(pkg)
    assert read_package(pkg).version == "1.0.0"

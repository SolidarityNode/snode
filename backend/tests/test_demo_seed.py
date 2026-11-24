from __future__ import annotations

import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from solidaritynode_backend.demo_seed import (
    TABLE_ORDER,
    ManifestError,
    gpkg_to_wkb,
    load_demo,
    read_gpkg_layer,
    verify_manifest,
)

BACKEND = Path(__file__).resolve().parents[1]
DEMO = BACKEND.parent / "data" / "synthetic" / "demo"
WKB_POINT = struct.pack("<BIdd", 1, 1, 1.0, 2.0)


@pytest.mark.parametrize(("envelope_code", "doubles"), [(0, 0), (1, 4), (2, 6), (4, 8)])
def test_gpkg_header_is_stripped(envelope_code: int, doubles: int) -> None:
    flags = 1 | (envelope_code << 1)
    blob = b"GP\x00" + bytes([flags]) + struct.pack("<i", 2100) + b"\x00" * 8 * doubles
    assert gpkg_to_wkb(blob + WKB_POINT) == WKB_POINT


def test_non_gpkg_blob_rejected() -> None:
    with pytest.raises(ValueError, match="GeoPackage"):
        gpkg_to_wkb(WKB_POINT)


def test_reads_demo_layers() -> None:
    units = read_gpkg_layer(DEMO / "demo.gpkg", "spatial_units")
    assert len(units) == 8
    assert all(u["geom"][:5] == b"\x01\x03\x00\x00\x00" for u in units)  # LE polygon WKB
    with pytest.raises(ValueError, match="not in"):
        read_gpkg_layer(DEMO / "demo.gpkg", "nope")


def test_load_demo_counts() -> None:
    counts = load_demo(DEMO).counts()
    assert counts == {
        "package": 1,
        "municipalities": 2,
        "spatial_units": 8,
        "population_groups": 3,
        "population": 24,
        "services": 2,
        "facilities": 4,
        "facility_services": 6,
        "network_nodes": 12,
        "network_edges": 26,
        "hand_check_travel_times": 128,
        "scenarios": 1,
    }
    assert set(counts) == set(TABLE_ORDER)


def test_tampered_file_is_rejected(tmp_path: Path) -> None:
    copy = tmp_path / "demo"
    shutil.copytree(DEMO, copy)
    verify_manifest(copy)
    (copy / "population.csv").write_text("unit_id,group_id,population\n", encoding="utf-8")
    with pytest.raises(ManifestError, match=r"population\.csv"):
        verify_manifest(copy)


def test_demo_migration_only_touches_schema_demo() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0001:0002", "--sql"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )
    sql = result.stdout
    assert "CREATE SCHEMA IF NOT EXISTS demo" in sql
    created = [
        line.split()[2] for line in sql.splitlines() if line.strip().startswith("CREATE TABLE")
    ]
    assert created
    assert all(name.startswith("demo.") for name in created), created

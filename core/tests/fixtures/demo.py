"""Read the synthetic demo dataset (``data/synthetic/demo/``) from files, for tests only.

Standard library only (``csv``, ``json``, ``sqlite3`` for the GeoPackage attribute tables), so
``core`` gains no dependency. Values are placeholders, never research parameters.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

DEMO_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "demo"


def read_csv(name: str) -> list[dict[str, str]]:
    with (DEMO_DIR / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_json(name: str) -> Any:
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))


def read_layer(layer: str) -> list[dict[str, Any]]:
    """Return the attribute rows of a GeoPackage layer (geometry column omitted)."""
    with sqlite3.connect(f"file:{DEMO_DIR / 'demo.gpkg'}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(f'SELECT * FROM "{layer}"').fetchall()
    # sqlite3.Row iterates over values, so .keys() is needed for column names.
    return [{k: row[k] for k in row.keys() if k != "geom"} for row in rows]  # noqa: SIM118


def gpkg_srs_ids() -> set[int]:
    with sqlite3.connect(f"file:{DEMO_DIR / 'demo.gpkg'}?mode=ro", uri=True) as db:
        return {r[0] for r in db.execute("SELECT srs_id FROM gpkg_geometry_columns")}

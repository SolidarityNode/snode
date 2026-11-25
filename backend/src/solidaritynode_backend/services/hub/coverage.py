"""Coverage matrix: municipality × layer (Spec 00 §3 Onboarding).

For every municipality known to the hub (in the registered boundaries or already onboarded),
and every layer of :data:`~.common.COVERAGE_LAYERS`, the status is ``missing``, ``open_data``,
``estimated`` or ``verified_by_municipality``: the **worst** quality among the layer's open
features of that municipality (``missing`` when it has none). With it: the layer version (the
version of the source the base step used, or the last approved facility changeset) and the last
update. ``transit`` and ``susceptibility`` stay ``missing`` in v0.2: no source of these kinds is
processed yet (susceptibility indicators belong to Paper 2).

The same matrix, restricted to a study area's municipalities, is the ``coverage`` of every
package manifest (ADR 0013).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.services.hub.base import boundary_municipalities
from solidaritynode_backend.services.hub.common import COVERAGE_LAYERS, worst_quality

__all__ = ["coverage_matrix", "municipality_coverage"]

_FEATURE_LAYER = {
    "boundaries": "municipalities",
    "spatial_units": "spatial_units",
    "population": "spatial_units",
    "network": "network_nodes",
    "facilities": "facilities",
}
_SOURCE_TYPE = {
    "boundaries": "boundaries",
    "spatial_units": "spatial_units",
    "population": "population",
    "network": "network",
}


def municipality_coverage(
    db: Session, municipalities: Iterable[str]
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return ``{municipality: {layer: {status, version, updated_at}}}``."""
    wanted = sorted(set(municipalities))
    out: dict[str, dict[str, dict[str, Any]]] = {
        m: {
            layer: {"status": "missing", "version": "-", "updated_at": None}
            for layer in COVERAGE_LAYERS
        }
        for m in wanted
    }
    qualities: dict[tuple[str, str], list[str]] = {}
    updated: dict[tuple[str, str], datetime] = {}
    for layer, mun, quality, has_population, last in db.execute(
        text(
            "SELECT layer, municipality_id, quality, "
            "(properties->'population') IS NOT NULL AND properties->'population' <> '{}'::jsonb, "
            "updated_at FROM hub_features WHERE municipality_id = ANY(:m) AND valid_to IS NULL"
        ),
        {"m": wanted},
    ):
        for cov, feature_layer in _FEATURE_LAYER.items():
            if feature_layer != layer or (cov == "population" and not has_population):
                continue
            qualities.setdefault((mun, cov), []).append(str(quality))
            key = (mun, cov)
            if key not in updated or last > updated[key]:
                updated[key] = last
    versions: dict[str, dict[str, str]] = {}
    for mun in wanted:
        row = db.execute(
            text(
                "SELECT inputs FROM hub_processing_records WHERE kind = 'onboarding_base' "
                "AND status = 'succeeded' AND outputs->'area_municipalities' ? :m "
                "ORDER BY finished_at DESC, id DESC LIMIT 1"
            ),
            {"m": mun},
        ).scalar_one_or_none()
        versions[mun] = {i["layer_type"]: str(i["version"]) for i in (row or [])}
    changesets = {
        str(m): (int(cid), at)
        for m, cid, at in db.execute(
            text(
                "SELECT DISTINCT ON (municipality_id) municipality_id, id, decided_at "
                "FROM hub_changesets WHERE status = 'approved' AND municipality_id = ANY(:m) "
                "ORDER BY municipality_id, decided_at DESC, id DESC"
            ),
            {"m": wanted},
        )
    }
    for mun in wanted:
        for layer in COVERAGE_LAYERS:
            entry = out[mun][layer]
            found = qualities.get((mun, layer))
            if found:
                entry["status"] = worst_quality(found)
                entry["updated_at"] = updated.get((mun, layer))
            if layer in _SOURCE_TYPE and found:
                entry["version"] = versions[mun].get(_SOURCE_TYPE[layer], "-")
            if layer == "facilities" and mun in changesets:
                entry["version"] = f"changeset {changesets[mun][0]}"
                entry["updated_at"] = changesets[mun][1]
    return out


def coverage_matrix(
    db: Session, settings: Settings, onboarded: bool | None = None
) -> list[dict[str, Any]]:
    """Return one row per municipality with its onboarding status and layer coverage.

    Args:
        db: Session.
        settings: Settings (to read the boundaries source).
        onboarded: ``True``: only municipalities whose base step is done; ``False``: only the
            others; ``None``: all.
    """
    names = dict(boundary_municipalities(settings, db))
    status = {
        str(m): (str(n), str(s))
        for m, n, s in db.execute(text("SELECT municipality_id, name, status FROM hub_onboarding"))
    }
    every = sorted(set(names) | set(status))
    coverage = municipality_coverage(db, every)
    rows = []
    for mun in every:
        name, state = status.get(mun, (names.get(mun, mun), "not_started"))
        is_onboarded = state != "not_started"
        if onboarded is not None and is_onboarded != onboarded:
            continue
        rows.append(
            {
                "municipality_id": mun,
                "name": name,
                "status": state,
                "onboarded": is_onboarded,
                "layers": coverage[mun],
            }
        )
    return rows

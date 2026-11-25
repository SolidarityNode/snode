"""Onboarding base step: incremental, stable ids, idempotent (Spec 00 §3; DP-003)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.hub.conftest import onboard


def _ids(db: Session, layer: str) -> dict[str, str]:
    return {
        str(f): str(m)
        for f, m in db.execute(
            text("SELECT feature_id, municipality_id FROM hub_features WHERE layer = :l"),
            {"l": layer},
        )
    }


@pytest.mark.usefixtures("demo_sources")
def test_onboarding_a_clips_a_and_its_neighbours(
    hub_db: Session, hub_settings: Any, hub_worker: Any
) -> None:
    record = onboard(hub_db, hub_settings, hub_worker, "M-A")
    assert record["status"] == "succeeded", record["checks"]
    assert record["outputs"]["area_municipalities"] == ["M-A", "M-B", "M-C"]
    units = _ids(hub_db, "spatial_units")
    assert sorted(units) == ["A1", "A2", "A3", "A4", "A5", "A6", "B1", "B2", "C1", "C2"]
    edges = _ids(hub_db, "network_edges")
    assert "E16" not in edges  # B1-D1: D is outside A's area
    assert {"E03", "E14"} <= set(edges)  # crossing A/B and A/C
    status = hub_db.execute(
        text("SELECT municipality_id, status FROM hub_onboarding ORDER BY 1")
    ).all()
    assert [tuple(s) for s in status] == [
        ("M-A", "base_ready"),
        ("M-B", "not_started"),
        ("M-C", "not_started"),
    ]
    a1 = hub_db.execute(
        text("SELECT properties FROM hub_features WHERE feature_id = 'A1'")
    ).scalar_one()
    assert a1["population"] == {"G-OLD": 310, "G-MOB": 95, "G-LOW": 220}
    assert a1["centroid_node_id"] == "N-A1"
    codes = {c["code"] for c in record["checks"]}
    assert "hub.base.centroid_rule" in codes
    assert not [c for c in record["checks"] if c["severity"] == "error"]


@pytest.mark.usefixtures("demo_sources")
def test_rerun_is_idempotent_and_neighbours_reuse_ids(
    hub_db: Session, hub_settings: Any, hub_worker: Any
) -> None:
    onboard(hub_db, hub_settings, hub_worker, "M-A")
    before = {
        layer: _ids(hub_db, layer) for layer in ("spatial_units", "network_nodes", "network_edges")
    }
    again = onboard(hub_db, hub_settings, hub_worker, "M-A")
    assert again["changed"] is False
    assert all(
        not v["added"] and not v["changed"] and not v["closed"]
        for v in again["outputs"]["layers"].values()
    )
    b = onboard(hub_db, hub_settings, hub_worker, "M-B")
    assert b["outputs"]["area_municipalities"] == ["M-A", "M-B", "M-D"]
    added = b["outputs"]["layers"]["spatial_units"]["added"]
    assert sorted(added) == ["D1", "D2"]  # A's and B's units were reused, not duplicated
    c = onboard(hub_db, hub_settings, hub_worker, "M-C")
    assert c["outputs"]["layers"]["spatial_units"]["added"] == []
    after = {
        layer: _ids(hub_db, layer) for layer in ("spatial_units", "network_nodes", "network_edges")
    }
    for layer, ids in before.items():
        assert {k: after[layer][k] for k in ids} == ids
    assert "E16" in after["network_edges"]
    count = hub_db.execute(
        text("SELECT count(*), count(DISTINCT (layer, feature_id)) FROM hub_features")
    ).one()
    assert count[0] == count[1]


def test_base_step_needs_every_source_type(hub_db: Session, hub_settings: Any) -> None:
    from solidaritynode_backend.jobs import PostgresJobRunner
    from solidaritynode_backend.services.hub.base import start_base
    from solidaritynode_backend.services.hub.common import HubError

    with pytest.raises(HubError, match="register these source types first"):
        start_base(hub_db, hub_settings, PostgresJobRunner(hub_db), "M-A", None)


def test_features_are_never_deleted(
    hub_db: Session, hub_settings: Any, hub_worker: Any, demo_sources: None
) -> None:
    onboard(hub_db, hub_settings, hub_worker, "M-A")
    with pytest.raises(Exception, match="never deleted"):
        hub_db.execute(text("DELETE FROM hub_features WHERE feature_id = 'A1'"))
    hub_db.rollback()

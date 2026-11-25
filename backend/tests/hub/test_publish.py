"""Publishing packages and propagating updates (ADR 0013; DP-006)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.hub.conftest import IMPORTS, onboard


def _import_facilities(db: Session, settings: Any, municipality: str, file: str) -> None:
    from solidaritynode_backend.services.hub.facilities import (
        ImportRequest,
        approve_changeset,
        create_import,
    )

    request = ImportRequest(municipality, source="Synthetic municipal register")
    cs = create_import(db, settings, request, file, (IMPORTS / file).read_bytes(), 1)
    approve_changeset(db, settings, cs, 1)
    db.commit()


def _publish(db: Session, settings: Any, worker: Any, area: str) -> dict[str, Any]:
    from solidaritynode_backend.jobs import PostgresJobRunner
    from solidaritynode_backend.services.hub.publish import start_publish

    started = start_publish(db, settings, PostgresJobRunner(db), area, "", 1)
    db.commit()
    worker.run_until_idle()
    row = (
        db.execute(text("SELECT * FROM hub_packages WHERE id = :i"), {"i": started["package_id"]})
        .mappings()
        .one()
    )
    db.commit()
    assert row["status"] == "published", row["error"]
    return dict(row)


def _area(db: Session, settings: Any, area: str, core: str) -> None:
    from solidaritynode_backend.services.hub.publish import create_study_area

    create_study_area(db, settings, area, f"Study area {core}", [core], None, None, 1)
    db.commit()


def _package_dir(settings: Any, row: dict[str, Any]) -> Path:
    return settings.hub_storage_dir / "packages" / row["study_area_id"] / row["version"]


@pytest.fixture
def a_published(
    hub_db: Session, hub_settings: Any, hub_worker: Any, demo_sources: None, hub_users: Any
) -> dict[str, Any]:
    onboard(hub_db, hub_settings, hub_worker, "M-A")
    _import_facilities(hub_db, hub_settings, "M-A", "facilities-M-A.csv")
    _area(hub_db, hub_settings, "study-area-a", "M-A")
    return _publish(hub_db, hub_settings, hub_worker, "study-area-a")


def test_first_package_is_valid_and_immutable(
    hub_db: Session, hub_settings: Any, a_published: dict[str, Any]
) -> None:
    from solidaritynode_backend.services.packages import read_package

    assert a_published["version"] == "1.0.0"
    content = read_package(_package_dir(hub_settings, a_published))
    m = content.manifest
    assert m["schema_version"] == "2.1"
    assert m["study_area"]["core_municipalities"] == ["M-A"]
    assert m["study_area"]["buffer_municipalities"] == ["M-B", "M-C"]
    assert m["coverage"]["M-A"]["facilities"]["status"] == "verified_by_municipality"
    assert m["coverage"]["M-B"]["facilities"]["status"] == "missing"
    assert set(m["coverage"]["M-A"]) >= {"spatial_units", "susceptibility"}
    assert {"DP-003", "DP-004", "DP-005", "DP-006"} <= set(m["processing_notes"])
    assert m["changelog"][-1]["version"] == "1.0.0"
    assert sorted(content.features["facilities"]) == ["HF-000001", "HF-000002", "HF-000003"]
    assert content.features["spatial_units"]["B1"][0]["role"] == "buffer"
    assert content.features["spatial_units"]["A1"][0]["role"] == "core"
    status = hub_db.execute(
        text("SELECT status FROM hub_onboarding WHERE municipality_id = 'M-A'")
    ).scalar_one()
    assert status == "published"
    with pytest.raises(Exception, match="immutable"):
        hub_db.execute(
            text("UPDATE hub_packages SET comment = 'x' WHERE id = :i"), {"i": a_published["id"]}
        )
    hub_db.rollback()


def test_onboarding_b_marks_a_for_update_and_b_arrives_as_verified_buffer(
    hub_db: Session,
    hub_settings: Any,
    hub_worker: Any,
    a_published: dict[str, Any],
    db: Session,
    settings: Any,
) -> None:
    from solidaritynode_backend.jobs import PostgresJobRunner
    from solidaritynode_backend.services.hub.common import HubError
    from solidaritynode_backend.services.hub.publish import list_study_areas, start_publish
    from solidaritynode_backend.services.packages import import_package, read_package

    def area_a() -> dict[str, Any]:
        return next(a for a in list_study_areas(hub_db) if a["id"] == "study-area-a")

    assert area_a()["update_available"] is False
    runner = PostgresJobRunner(hub_db)
    with pytest.raises(HubError, match="nothing to publish"):
        start_publish(hub_db, hub_settings, runner, "study-area-a", "", 1)
    hub_db.rollback()
    onboard(hub_db, hub_settings, hub_worker, "M-B")
    assert area_a()["update_available"] is False  # only D's features were added
    _import_facilities(hub_db, hub_settings, "M-B", "facilities-M-B.csv")
    pending = area_a()
    assert pending["update_available"] is True
    assert pending["pending"]["next_version"] == "1.1.0"
    assert "(M-B): 1 added" in pending["pending"]["changelog"]

    second = _publish(hub_db, hub_settings, hub_worker, "study-area-a")
    assert second["version"] == "1.1.0"
    content = read_package(_package_dir(hub_settings, second))
    f4 = content.features["facilities"]["HF-000004"][0]
    assert (f4["role"], f4["quality"], f4["municipality_id"]) == (
        "buffer",
        "verified_by_municipality",
        "M-B",
    )
    assert content.manifest["coverage"]["M-B"]["facilities"]["status"] == "verified_by_municipality"
    assert [c["version"] for c in content.manifest["changelog"]] == ["1.0.0", "1.1.0"]
    assert area_a()["update_available"] is False

    # Both versions import into a municipal installation with the existing import flow.
    first = read_package(_package_dir(hub_settings, a_published))
    import_package(db, settings, first, None)
    db.commit()
    warned_1 = sorted(r[0] for r in db.execute(text("SELECT DISTINCT unit_id FROM data_warnings")))
    assert warned_1 == ["A3", "A4", "A5", "A6"]
    outcome = import_package(db, settings, content, None)
    db.commit()
    assert outcome.preview["status"] == "update"
    assert outcome.preview["layers"]["facilities"]["added"] == ["HF-000004"]
    warned_2 = sorted(
        r[0]
        for r in db.execute(
            text("SELECT DISTINCT unit_id FROM data_warnings WHERE data_version_id = :d"),
            {"d": outcome.data_version_id},
        )
    )
    assert warned_2 == ["A4", "A5"]  # next to C, still without facilities


def test_shared_features_have_the_same_ids_in_every_package(
    hub_db: Session, hub_settings: Any, hub_worker: Any, a_published: dict[str, Any]
) -> None:
    from solidaritynode_backend.services.packages import read_package

    onboard(hub_db, hub_settings, hub_worker, "M-B")
    onboard(hub_db, hub_settings, hub_worker, "M-C")
    _area(hub_db, hub_settings, "study-area-b", "M-B")
    _area(hub_db, hub_settings, "study-area-c", "M-C")
    packages = {
        "a": read_package(_package_dir(hub_settings, a_published)),
        "b": read_package(
            _package_dir(hub_settings, _publish(hub_db, hub_settings, hub_worker, "study-area-b"))
        ),
        "c": read_package(
            _package_dir(hub_settings, _publish(hub_db, hub_settings, hub_worker, "study-area-c"))
        ),
    }
    for layer in ("spatial_units", "network_nodes", "network_edges", "facilities"):
        seen: dict[str, tuple[Any, ...]] = {}
        for content in packages.values():
            for fid, (props, wkb) in content.features[layer].items():
                key = (
                    wkb,
                    json.dumps(
                        {k: v for k, v in props.items() if k not in ("role", "_geometry_sha256")},
                        sort_keys=True,
                        default=str,
                    ),
                )
                assert seen.setdefault(fid, key) == key, f"{layer}/{fid} differs between packages"
    assert set(packages["a"].features["spatial_units"]) & set(
        packages["b"].features["spatial_units"]
    ) >= {"A3", "A6", "B1", "B2"}
    assert set(packages["c"].features["spatial_units"]) == {
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "C1",
        "C2",
    }

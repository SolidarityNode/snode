"""The same facility file gives the same validation in the hub and in a municipal installation.

ADR 0014 Part A, decision 23: one validator, two feature sources. Location checks depend on
each side's data and are compared only where both sides have the same data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.hub.conftest import IMPORTS, onboard
from tests.hub.test_publish import _area, _import_facilities, _package_dir, _publish

LOCATION = {"hub.import.outside_municipality", "hub.import.no_unit", "hub.import.duplicate_near"}


def _validate(db: Session, settings: Any, source: Any, name: str, data: bytes) -> tuple[Any, Any]:
    from solidaritynode_backend.services.hub.facilities import (
        ImportRequest,
        build_changeset,
        parse_file,
    )

    parsed = parse_file(settings, name, data)
    request = ImportRequest("M-A", source="test")
    return build_changeset(db, settings, request, parsed, source)


def _summary(items: list[dict[str, Any]], report: list[dict[str, Any]]) -> tuple[Any, Any]:
    entries = sorted(
        (e["code"], e["severity"], tuple(sorted((k, str(v)) for k, v in e["params"].items())))
        for e in report
        if e["code"] not in LOCATION
    )
    changes = sorted((i["action"], i["facility_id"] or "", tuple(i["fields"])) for i in items)
    return entries, changes


@pytest.fixture
def both_roles(
    hub_db: Session,
    hub_settings: Any,
    hub_worker: Any,
    demo_sources: None,
    hub_users: Any,
    db: Session,
    settings: Any,
) -> int:
    """A hub with M-A onboarded and published, and the package imported in a municipality."""
    from solidaritynode_backend.services.packages import import_package, read_package

    onboard(hub_db, hub_settings, hub_worker, "M-A")
    _import_facilities(hub_db, hub_settings, "M-A", "facilities-M-A.csv")
    _area(hub_db, hub_settings, "study-area-a", "M-A")
    package = _publish(hub_db, hub_settings, hub_worker, "study-area-a")
    outcome = import_package(db, settings, read_package(_package_dir(hub_settings, package)), None)
    db.commit()
    return outcome.data_version_id


@pytest.mark.parametrize(
    "file",
    [
        "facilities-M-A.csv",
        "facilities-M-A-update.csv",
        "facilities-M-A-errors.csv",
        "facilities-M-A-personal.csv",
    ],
)
def test_same_file_same_report_in_both_roles(
    file: str,
    both_roles: int,
    hub_db: Session,
    hub_settings: Any,
    db: Session,
    settings: Any,
) -> None:
    from solidaritynode_backend.services.hub.facilities import (
        DataVersionFeatureSource,
        HubFeatureSource,
    )

    data = (IMPORTS / file).read_bytes()
    hub = _validate(hub_db, hub_settings, HubFeatureSource(hub_db, hub_settings), file, data)
    municipal = _validate(db, settings, DataVersionFeatureSource(db, both_roles), file, data)
    assert _summary(*hub) == _summary(*municipal)


def test_municipality_validates_core_municipalities_only(
    both_roles: int, db: Session, settings: Any
) -> None:
    from solidaritynode_backend.services.hub.common import HubError
    from solidaritynode_backend.services.hub.facilities import (
        DataVersionFeatureSource,
        ImportRequest,
        build_changeset,
        parse_file,
    )

    data = (IMPORTS / "facilities-M-B.csv").read_bytes()
    parsed = parse_file(settings, "b.csv", data)
    with pytest.raises(HubError, match="not a core municipality"):
        build_changeset(
            db,
            settings,
            ImportRequest("M-B", source="x"),
            parsed,
            DataVersionFeatureSource(db, both_roles),
        )
    assert db.execute(text("SELECT count(*) FROM data_versions")).scalar_one() == 1
    assert Path(IMPORTS).exists()

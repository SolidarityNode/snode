"""Facility import, changesets and history (DP-004)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.hub.conftest import IMPORTS, onboard


@pytest.fixture
def onboarded_a(hub_db: Session, hub_settings: Any, hub_worker: Any, demo_sources: None) -> None:
    record = onboard(hub_db, hub_settings, hub_worker, "M-A")
    assert record["status"] == "succeeded"


def _import(
    db: Session,
    settings: Any,
    path: Path | str,
    *,
    data: bytes | None = None,
    complete: bool = False,
    municipality: str = "M-A",
    user: int = 1,
) -> dict[str, Any]:
    from solidaritynode_backend.services.hub.facilities import (
        ImportRequest,
        changeset_detail,
        create_import,
    )

    name = Path(path).name
    content = data if data is not None else Path(path).read_bytes()
    request = ImportRequest(
        municipality, source="Synthetic municipal register", complete_list=complete
    )
    changeset_id = create_import(db, settings, request, name, content, user)
    db.commit()
    return changeset_detail(db, changeset_id)


def _approve(db: Session, settings: Any, changeset_id: int, **kwargs: Any) -> dict[str, Any]:
    from solidaritynode_backend.services.hub.facilities import approve_changeset

    result = approve_changeset(db, settings, changeset_id, 1, **kwargs)
    db.commit()
    return result


def _codes(cs: dict[str, Any], severity: str | None = None) -> list[str]:
    return [
        e["code"] for e in cs["report"]["entries"] if severity is None or e["severity"] == severity
    ]


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_valid_file_adds_facilities_with_stable_ids(hub_db: Session, hub_settings: Any) -> None:
    cs = _import(hub_db, hub_settings, IMPORTS / "facilities-M-A.csv")
    assert cs["report"]["errors"] == 0
    assert cs["report"]["summary"] == {"add": 3, "update": 0, "close": 0}
    result = _approve(hub_db, hub_settings, cs["id"])
    assert result["added"] == ["HF-000001", "HF-000002", "HF-000003"]
    f1 = hub_db.execute(
        text("SELECT properties, quality FROM hub_features WHERE feature_id = 'HF-000001'")
    ).one()
    assert f1.quality == "verified_by_municipality"
    assert f1.properties["node_id"] == "N-F1"
    assert f1.properties["unit_id"] == "A2"
    assert f1.properties["services"]["S-SD"] == {
        "places": 10.0,
        "staff": 2.0,
        "throughput": 120.0,
        "throughput_unit": "appointment",
    }
    status = hub_db.execute(
        text("SELECT status FROM hub_onboarding WHERE municipality_id = 'M-A'")
    ).scalar_one()
    assert status == "facilities_in_progress"
    record = (
        hub_db.execute(
            text("SELECT * FROM hub_processing_records WHERE id = :r"), {"r": result["record_id"]}
        )
        .mappings()
        .one()
    )
    assert record["processing_note"] == "DP-004"
    assert record["inputs"][0]["sha256"] == cs["file_sha256"]


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_file_with_errors_lists_them_and_cannot_be_approved(
    hub_db: Session, hub_settings: Any
) -> None:
    from solidaritynode_backend.services.hub.common import HubError

    cs = _import(hub_db, hub_settings, IMPORTS / "facilities-M-A-errors.csv")
    errors = {
        (e["code"], e["params"].get("row"))
        for e in cs["report"]["entries"]
        if e["severity"] == "error"
    }
    assert ("hub.import.required", 2) in errors  # name missing
    assert ("hub.import.unknown_service", 3) in errors  # S-XX
    assert ("hub.import.wrong_unit", 4) in errors  # visit for an appointment service
    assert ("hub.import.outside_municipality", 5) in errors  # point in M-B
    assert cs["report"]["errors"] == 4
    with pytest.raises(HubError, match="has errors"):
        _approve(hub_db, hub_settings, cs["id"])


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_personal_data_columns_and_values_are_dropped_and_reported(
    hub_db: Session, hub_settings: Any
) -> None:
    cs = _import(hub_db, hub_settings, IMPORTS / "facilities-M-A-personal.csv")
    warnings = [e for e in cs["report"]["entries"] if e["severity"] == "warning"]
    dropped = {e["params"]["column"] for e in warnings if e["code"] == "hub.import.personal_column"}
    assert dropped == {"contact_person", "mobile"}
    assert any(
        e["code"] == "hub.import.personal_value" and e["params"]["row"] == 2 for e in warnings
    )
    assert cs["report"]["errors"] == 0
    stored = str(cs["items"])
    for personal in ("Maria", "6900000000", "6912345678"):
        assert personal not in stored
    _approve(hub_db, hub_settings, cs["id"])
    everything = str(hub_db.execute(text("SELECT properties FROM hub_features")).all())
    assert "Maria" not in everything
    assert "6912345678" not in everything


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_reimport_with_one_change_shows_exactly_that_field(
    hub_db: Session, hub_settings: Any
) -> None:
    from solidaritynode_backend.services.hub.facilities import facility_history

    _approve(
        hub_db, hub_settings, _import(hub_db, hub_settings, IMPORTS / "facilities-M-A.csv")["id"]
    )
    text_ = (IMPORTS / "facilities-M-A.csv").read_text(encoding="utf-8")
    changed = text_.replace(",S-SD,8,2,100,", ",S-SD,8,2,90,")
    assert changed != text_
    cs = _import(hub_db, hub_settings, "facilities-M-A-v2.csv", data=changed.encode())
    assert cs["report"]["summary"] == {"add": 0, "update": 1, "close": 0}
    (item,) = cs["items"]
    assert item["facility_id"] == "HF-000002"  # matched by external id REG-F2
    assert item["fields"] == ["services.S-SD.throughput"]
    assert "hub.import.matched_external" in _codes(cs, "info")
    _approve(hub_db, hub_settings, cs["id"])
    history = facility_history(hub_db, "HF-000002")
    assert [h["action"] for h in history] == ["add", "update"]
    assert history[1]["fields"] == ["services.S-SD.throughput"]
    assert history[1]["source"] == "Synthetic municipal register"
    assert history[1]["created_by_name"] == "admin"


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_partial_import_keeps_missing_facilities_and_complete_list_closes_them(
    hub_db: Session, hub_settings: Any
) -> None:
    from solidaritynode_backend.services.hub.common import HubError

    _approve(
        hub_db, hub_settings, _import(hub_db, hub_settings, IMPORTS / "facilities-M-A.csv")["id"]
    )
    rows = list(csv.DictReader(io.StringIO((IMPORTS / "facilities-M-A.csv").read_text())))
    only_f1 = [r for r in rows if r["external_id"] == "REG-F1"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(only_f1)
    data = buffer.getvalue().encode()

    partial = _import(hub_db, hub_settings, "only-f1.csv", data=data)
    assert partial["report"]["summary"] == {"add": 0, "update": 0, "close": 0}
    assert partial["items"] == []

    complete = _import(hub_db, hub_settings, "only-f1.csv", data=data, complete=True)
    assert complete["report"]["summary"] == {"add": 0, "update": 0, "close": 2}
    assert "hub.import.complete_list" in _codes(complete, "warning")
    with pytest.raises(HubError, match=r"type the number of facilities that will be closed \(2\)"):
        _approve(hub_db, hub_settings, complete["id"], confirm_close=1)
    hub_db.rollback()
    result = _approve(hub_db, hub_settings, complete["id"], confirm_close=2)
    assert result["closed"] == ["HF-000002", "HF-000003"]
    closed = hub_db.execute(
        text(
            "SELECT feature_id, valid_to FROM hub_features WHERE layer = 'facilities' "
            "ORDER BY feature_id"
        )
    ).all()
    assert [c.valid_to is not None for c in closed] == [False, True, True]  # kept, not deleted


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_xlsx_template_round_trip_and_unknown_id(hub_db: Session, hub_settings: Any) -> None:
    from openpyxl import load_workbook

    from solidaritynode_backend.services.hub.facilities import COLUMNS, template_file

    content, _, _ = template_file(hub_settings, "xlsx")
    workbook = load_workbook(io.BytesIO(content))
    assert workbook.sheetnames == ["facilities", "instructions"]
    instructions = [r for r in workbook["instructions"].iter_rows(values_only=True)]
    assert instructions[0] == (
        "column / στήλη",
        "required / υποχρεωτικό",
        "description",
        "περιγραφή",
    )
    assert any("προσωπικά δεδομένα" in str(r[3]) for r in instructions)
    sheet = workbook["facilities"]
    assert [c.value for c in sheet[1]] == list(COLUMNS)
    sheet["A2"] = "HF-999999"  # the example row now names an unknown facility
    out = io.BytesIO()
    workbook.save(out)
    cs = _import(hub_db, hub_settings, "edited.xlsx", data=out.getvalue())
    assert ("hub.import.unknown_id", 2) in {
        (e["code"], e["params"].get("row")) for e in cs["report"]["entries"]
    }


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_exports_escape_formulas(hub_db: Session, hub_settings: Any) -> None:
    from openpyxl import load_workbook

    from solidaritynode_backend.services.hub.facilities import facilities_export, report_export
    from solidaritynode_backend.services.hub.spreadsheet import escape_cell

    assert escape_cell("=1+1") == "'=1+1"
    assert escape_cell("+30 210") == "'+30 210"
    assert escape_cell("-x") == "'-x"
    assert escape_cell("@SUM(A1)") == "'@SUM(A1)"
    assert escape_cell("plain") == "plain"
    assert escape_cell(-5) == -5
    data = (
        (IMPORTS / "facilities-M-A.csv")
        .read_text()
        .replace("Synthetic municipal register (fictional)", '=HYPERLINK("http://x")')
        .replace(",community_centre,", ",@cmd,")
    )
    cs = _import(hub_db, hub_settings, "formula.csv", data=data.encode())
    _approve(hub_db, hub_settings, cs["id"])
    content, _, _ = facilities_export(hub_db, "M-A", "csv")
    exported = content.decode()
    assert "'=HYPERLINK" in exported
    assert "'@cmd" in exported
    assert ",=HYPERLINK" not in exported
    xlsx, _, _ = facilities_export(hub_db, "M-A", "xlsx")
    cells = [
        c
        for row in load_workbook(io.BytesIO(xlsx))["facilities"].iter_rows(values_only=True)
        for c in row
    ]
    assert all(not (isinstance(c, str) and c.startswith(("=", "@", "+", "-"))) for c in cells)
    errors = _import(hub_db, hub_settings, IMPORTS / "facilities-M-A-errors.csv")
    report, _, _ = report_export(hub_db, errors["id"], "csv")
    assert report.decode().splitlines()[0] == "severity,row,column,code,message"


@pytest.mark.usefixtures("hub_users", "demo_sources")
def test_import_needs_the_base_step(hub_db: Session, hub_settings: Any) -> None:
    from solidaritynode_backend.services.hub.common import HubError

    with pytest.raises(HubError, match="no base data yet"):
        _import(hub_db, hub_settings, IMPORTS / "facilities-M-B.csv", municipality="M-B")


@pytest.mark.usefixtures("onboarded_a", "hub_users")
def test_manual_edit_creates_the_same_kind_of_changeset(hub_db: Session, hub_settings: Any) -> None:
    from solidaritynode_backend.services.hub.facilities import changeset_detail, manual_changeset

    _approve(
        hub_db, hub_settings, _import(hub_db, hub_settings, IMPORTS / "facilities-M-A.csv")["id"]
    )
    current = hub_db.execute(
        text(
            "SELECT properties, ST_X(geom), ST_Y(geom) FROM hub_features "
            "WHERE feature_id = 'HF-000003'"
        )
    ).one()
    props = current[0]
    values = {k: props.get(k) for k in ("name", "facility_type", "operating_hours", "public_phone")}
    values.update(
        {
            "quality": "verified_by_municipality",
            "x": current[1],
            "y": current[2],
            "operating_hours": "Mon-Sat 08:00-14:00",
        }
    )
    services = [
        {
            "service_id": "S-HC",
            "places": 12,
            "staff": 3,
            "throughput": 110,
            "throughput_unit": "hour",
        }
    ]
    cs_id = manual_changeset(
        hub_db, hub_settings, "M-A", "HF-000003", values, services, False, "Saturday opening", 1
    )
    hub_db.commit()
    cs = changeset_detail(hub_db, cs_id)
    assert cs["kind"] == "manual"
    assert cs["report"]["errors"] == 0, cs["report"]["entries"]
    assert [i["fields"] for i in cs["items"]] == [["operating_hours"]]
    closing = manual_changeset(hub_db, hub_settings, "M-A", "HF-000001", {}, [], True, "Closed", 1)
    hub_db.commit()
    assert [i["action"] for i in changeset_detail(hub_db, closing)["items"]] == ["close"]

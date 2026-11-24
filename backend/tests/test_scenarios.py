"""Scenarios: validation, versioning, duplicate, delete and the JSON Schema (ADR 0016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from solidaritynode_backend.schemas.scenario import ScenarioBody, export_json_schema
from tests.conftest import CLOSE_E02, REPO, import_version

SCHEMA_FILE = REPO / "docs" / "schemas" / "scenario.schema.json"


def test_json_schema_export_is_current(tmp_path: Path) -> None:
    export_json_schema(tmp_path / "s.json")
    assert SCHEMA_FILE.read_text() == (tmp_path / "s.json").read_text(), "run `make schemas`"
    schema = json.loads(SCHEMA_FILE.read_text())
    assert schema["properties"]["schema_version"]["const"] == "1.0"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"severities": [{"facility_id": "F1", "severity": 1.5}]}, "less than or equal to 1"),
        ({"severities": [{"facility_id": "F1", "severity": 0.5}]}, "rationing case"),
        ({"reference_level": "minor"}, "reference scenarios"),
        ({"schema_version": "9.9"}, "schema_version"),
        ({"unknown": 1}, "Extra inputs"),
        (
            {
                "capacity_changes": [
                    {
                        "facility_id": "F1",
                        "service_id": "S-HC",
                        "capacity_input": "beds",
                        "mode": "relative",
                        "amount": 1,
                    }
                ]
            },
            "capacity_input",
        ),
    ],
)
def test_schema_rules(body: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ScenarioBody.model_validate(body)


def test_validate_returns_errors_without_saving(as_admin, as_analyst) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    bad = as_analyst.post(
        "/scenarios/validate",
        json={"name": "", "body": {"severities": [{"facility_id": "F1", "severity": 2}]}},
    ).json()
    assert bad["valid"] is False
    assert {tuple(e["loc"]) for e in bad["errors"]} >= {
        ("name",),
        ("body", "severities", "0", "severity"),
    }
    missing = as_analyst.post(
        "/scenarios/validate",
        json={
            "name": "x",
            "body": {"severities": [{"facility_id": "F4", "severity": 1}], "rationing": "uniform"},
        },
    ).json()
    assert missing["problems"] == ["facility F4: closed or missing in data 1.0.0"]
    assert as_analyst.post("/scenarios/validate", json=CLOSE_E02).json()["valid"] is True
    assert as_analyst.get("/scenarios").json() == [
        s for s in as_analyst.get("/scenarios").json() if s["is_baseline"]
    ]


def test_create_refuses_unresolved_references(as_admin, as_analyst) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    body = {
        **CLOSE_E02,
        "body": {"closed_edges": {"edge_ids": ["E01"], "modes": ["walk"]}, "rationing": "uniform"},
    }
    response = as_analyst.post("/scenarios", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["problems"] == [
        "edge E01: cannot be closed (closable = false)"
    ]


def test_versioning_duplicate_and_delete(as_admin, as_analyst, worker) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    created = as_analyst.post("/scenarios", json=CLOSE_E02).json()
    sid = created["id"]
    assert created["latest_version"] == 1
    assert created["data_version"]["version"] == "1.0.0"
    edited = {
        **CLOSE_E02,
        "name": "Close E02 and F1 half",
        "body": {**CLOSE_E02["body"], "severities": [{"facility_id": "F1", "severity": 0.5}]},
    }
    updated = as_analyst.put(f"/scenarios/{sid}", json=edited).json()
    assert updated["latest_version"] == 2
    assert updated["versions"] == [1, 2]
    v1 = as_analyst.get(f"/scenarios/{sid}/versions/1").json()
    assert v1["name"] == "Close E02"
    assert v1["body"]["severities"] == []
    copy = as_analyst.post(f"/scenarios/{sid}/duplicate").json()
    assert copy["name"] == "Copy of Close E02 and F1 half"
    assert copy["visibility"] == "private"
    assert copy["latest_version"] == 1
    # Hard delete is refused once runs exist; soft delete hides the scenario.
    assert as_analyst.post("/runs", json={"scenario_id": sid}).status_code == 201
    refused = as_analyst.delete(f"/scenarios/{sid}", params={"hard": True})
    assert refused.status_code == 409
    assert as_analyst.delete(f"/scenarios/{copy['id']}", params={"hard": True}).status_code == 204
    assert as_analyst.delete(f"/scenarios/{sid}").status_code == 204
    assert as_analyst.get(f"/scenarios/{sid}").status_code == 404
    ids = {s["id"] for s in as_analyst.get("/scenarios").json()}
    assert sid not in ids


def test_list_filters_by_owner_and_visibility(as_admin, as_analyst) -> None:  # type: ignore[no-untyped-def]
    import_version(as_admin, "1.0.0")
    mine = as_analyst.post("/scenarios", json={**CLOSE_E02, "visibility": "private"}).json()
    as_admin.post("/scenarios", json=CLOSE_E02)
    own = as_analyst.get("/scenarios", params={"owner": "me"}).json()
    assert [s["id"] for s in own] == [mine["id"]]
    shared = as_analyst.get("/scenarios", params={"visibility": "shared"}).json()
    assert mine["id"] not in {s["id"] for s in shared}
    assert any(s["is_baseline"] for s in shared)

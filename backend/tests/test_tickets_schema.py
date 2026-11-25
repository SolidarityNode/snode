from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from solidaritynode_core.model import TICKET_FIELDS, Ticket

from solidaritynode_backend.schemas.tickets import TicketRequest, TicketResponse

T0 = datetime(2030, 1, 1, 9, tzinfo=UTC)
VALID = {
    "unit": "U-A",
    "group": "G-older",
    "service": "S-homecare",
    "facility_id": "F-1",
    "requested_at": T0.isoformat(),
    "scheduled_at": (T0 + timedelta(days=1)).isoformat(),
    "first_request_in_period": True,
}


def test_schema_mirrors_core_ticket() -> None:
    assert set(TicketRequest.model_fields) == TICKET_FIELDS
    assert set(TicketResponse.model_fields) == {f.name for f in dataclasses.fields(Ticket)}


def test_valid_ticket_round_trips() -> None:
    request = TicketRequest.model_validate(VALID)
    core = request.to_core()
    assert core.unit == "U-A"
    assert TicketResponse.from_core(core).model_dump() == request.model_dump()


@pytest.mark.parametrize("extra", ["name", "phone", "email", "address", "device_id", "id"])
def test_personal_or_unknown_fields_are_rejected(extra: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TicketRequest.model_validate({**VALID, extra: "x"})


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        TicketRequest.model_validate({**VALID, "requested_at": "2030-01-01T09:00:00"})


def test_inconsistent_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="precede"):
        TicketRequest.model_validate(
            {**VALID, "fulfilled_at": (T0 - timedelta(hours=1)).isoformat()}
        )


def test_identifiers_are_constrained() -> None:
    with pytest.raises(ValidationError):
        TicketRequest.model_validate({**VALID, "unit": "Main Street 12, Athens"})


def test_facility_is_required() -> None:
    """OQ-29: the facility where the request is made is a required ticket field."""
    body = {k: v for k, v in VALID.items() if k != "facility_id"}
    with pytest.raises(ValidationError, match="facility_id"):
        TicketRequest.model_validate(body)
    assert TicketRequest.model_validate(VALID).to_core().facility_id == "F-1"

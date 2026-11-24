"""Tickets are anonymous by design (Paper 4 §4.1; OQ-8, OQ-21; AGENTS.md privacy rules)."""

from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta

import pytest

from solidaritynode_core.model import TICKET_FIELDS, Period, RecordingCoverage, Ticket
from tests.fixtures import synthetic

FORBIDDEN = re.compile(
    r"name|surname|email|phone|mobile|address|street|contact|device|imei|mac|ip_|"
    r"person|patient|citizen|user|requester|amka|afm|ssn|passport|birth|dob|age|gender|"
    r"lat|lon|coord|geom|location|token|cookie|hash",
    re.IGNORECASE,
)


def test_ticket_has_exactly_the_allowed_fields() -> None:
    names = {f.name for f in dataclasses.fields(Ticket)}
    assert names == TICKET_FIELDS
    assert names == {
        "unit",
        "group",
        "service",
        "requested_at",
        "scheduled_at",
        "fulfilled_at",
        "expires_at",
        "first_request_in_period",
    }


def test_ticket_has_no_personal_data_fields() -> None:
    offending = [f.name for f in dataclasses.fields(Ticket) if FORBIDDEN.search(f.name)]
    assert offending == []


def test_first_request_flag_is_boolean_not_identifier() -> None:
    hints = {f.name: f.type for f in dataclasses.fields(Ticket)}
    assert hints["first_request_in_period"] in (bool, "bool")


def test_ticket_requires_timezone_aware_times() -> None:
    with pytest.raises(ValueError, match="timezone"):
        synthetic.ticket(requested_at=datetime(2030, 1, 1))


def test_ticket_times_not_before_request() -> None:
    with pytest.raises(ValueError, match="precede"):
        synthetic.ticket(fulfilled_at=synthetic.T0 - timedelta(hours=1))


def test_recording_coverage_bounds() -> None:
    period = Period(synthetic.T0, synthetic.T0 + timedelta(days=7))
    assert RecordingCoverage(synthetic.FACILITIES[0], period, 1.0).is_full
    unknown = RecordingCoverage(synthetic.FACILITIES[0], period, None)
    assert not unknown.is_known
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        RecordingCoverage(synthetic.FACILITIES[0], period, 1.5)
    with pytest.raises(ValueError, match="after"):
        Period(synthetic.T0, synthetic.T0)

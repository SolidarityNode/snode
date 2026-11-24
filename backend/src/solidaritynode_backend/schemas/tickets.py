"""Anonymous ticket schemas mirroring ``solidaritynode_core.model.Ticket`` (Paper 4 §4.1).

Only the fields of the core ticket are accepted; unknown fields are **rejected**, so no personal
data (names, contacts, addresses, device identifiers) can slip in (AGENTS.md privacy rules;
OQ-21). The facility where the request is made is recorded (OQ-29) and follows the same privacy
rules. Group handling for people in several groups is open (OQ-6). Nothing is persisted until
ADR 0010 is accepted.
"""

from __future__ import annotations

from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from solidaritynode_core.model import FacilityId, GroupId, ServiceId, Ticket, UnitId

__all__ = ["TicketRequest", "TicketResponse"]

_ID = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")


class _TicketFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: str = _ID
    group: str = _ID
    service: str = _ID
    facility_id: str = _ID
    requested_at: AwareDatetime
    scheduled_at: AwareDatetime | None = None
    fulfilled_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    first_request_in_period: bool

    @model_validator(mode="after")
    def _validate_with_core(self) -> Self:
        self.to_core()  # raises ValueError -> 422 on inconsistent timestamps
        return self

    def to_core(self) -> Ticket:
        """Convert to the core domain ticket."""
        return Ticket(
            unit=UnitId(self.unit),
            group=GroupId(self.group),
            service=ServiceId(self.service),
            facility_id=FacilityId(self.facility_id),
            requested_at=self.requested_at,
            scheduled_at=self.scheduled_at,
            fulfilled_at=self.fulfilled_at,
            expires_at=self.expires_at,
            first_request_in_period=self.first_request_in_period,
        )


class TicketRequest(_TicketFields):
    """An anonymous request as submitted (for example from a QR form). Paper 4 §4.1."""


class TicketResponse(_TicketFields):
    """An anonymous request as returned by the API. Carries no identifier (OQ-21)."""

    @classmethod
    def from_core(cls, ticket: Ticket) -> TicketResponse:
        """Build from a core ticket."""
        return cls(
            unit=ticket.unit,
            group=ticket.group,
            service=ticket.service,
            facility_id=ticket.facility_id,
            requested_at=ticket.requested_at,
            scheduled_at=ticket.scheduled_at,
            fulfilled_at=ticket.fulfilled_at,
            expires_at=ticket.expires_at,
            first_request_in_period=ticket.first_request_in_period,
        )

"""Anonymous request tickets and recording coverage (Paper 4 §4.1; OQ-8, OQ-21).

Tickets are **anonymous by design** (AGENTS.md, "Data and privacy rules"): they store only the
spatial unit of origin, the social group, the service, the facility where the request is made or
scheduled (OQ-29) and timestamps, plus a yes/no flag "first request in this period" that lets
people be counted without being identified (OQ-8).
No names, contact details, exact addresses or device identifiers. Re-identification risk in
small units, minimum cell sizes and retention are **open** (OQ-21); the flag must never become
an identifier. The facility raises that risk further and is subject to the same rules (OQ-29,
ADR 0010); no ticket is stored until they are decided.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from solidaritynode_core.model.ids import FacilityId, GroupId, ServiceId, UnitId

__all__ = ["TICKET_FIELDS", "Period", "RecordingCoverage", "Ticket"]


def _require_aware(name: str, value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Ticket:
    """One anonymous service request (Paper 4 §4.1; Spec 00 §4.4; OQ-6, OQ-8, OQ-21, OQ-29).

    Attributes:
        unit: Spatial unit of origin ``i``.
        group: Social group ``g``. Whether a ticket can carry several groups, or a priority
            rule applies, is open (OQ-6); the paper states a single group.
        service: Service (need) requested ``s``.
        facility_id: Facility ``f`` where the request is made or scheduled, in practice the
            facility that issues the QR code or appointment (OQ-29). Not personal data, but it
            raises re-identification risk in small units and follows the OQ-21 rules.
        requested_at: Request time ``t_r``.
        scheduled_at: Scheduled time ``t_a``, if any.
        fulfilled_at: Service (fulfilment) time ``t_f``, if fulfilled.
        expires_at: Expiry time ``t_e``, if any.
        first_request_in_period: ``True`` if this is the requester's first request in the
            reference period (OQ-8). A yes/no flag only, never an identifier (OQ-21).
    """

    unit: UnitId
    group: GroupId
    service: ServiceId
    facility_id: FacilityId
    requested_at: datetime
    scheduled_at: datetime | None
    fulfilled_at: datetime | None
    expires_at: datetime | None
    first_request_in_period: bool

    def __post_init__(self) -> None:
        """Validate timezone-awareness and that no timestamp precedes the request."""
        for name in ("requested_at", "scheduled_at", "fulfilled_at", "expires_at"):
            _require_aware(name, getattr(self, name))
        for name in ("scheduled_at", "fulfilled_at", "expires_at"):
            value: datetime | None = getattr(self, name)
            if value is not None and value < self.requested_at:
                raise ValueError(f"{name} must not precede requested_at")


#: The complete, closed set of ticket fields. Adding a field requires a privacy review (OQ-21).
TICKET_FIELDS: frozenset[str] = frozenset(
    {
        "unit",
        "group",
        "service",
        "facility_id",
        "requested_at",
        "scheduled_at",
        "fulfilled_at",
        "expires_at",
        "first_request_in_period",
    }
)


@dataclass(frozen=True, slots=True)
class Period:
    """Half-open time interval ``[start, end)`` (timezone-aware).

    Attributes:
        start: Inclusive start.
        end: Exclusive end; strictly after ``start``.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Validate timezone-awareness and ordering."""
        _require_aware("start", self.start)
        _require_aware("end", self.end)
        if self.end <= self.start:
            raise ValueError("Period end must be after start")


@dataclass(frozen=True, slots=True)
class RecordingCoverage:
    """Share of a facility's requests captured by the ticket system in a period (OQ-8).

    Observations are used for learning only where coverage is full or known (OQ-8). Tickets
    record their facility (OQ-29), but coverage (the share of requests captured at all) cannot be
    derived from tickets and is recorded separately per facility and period.

    Attributes:
        facility: Facility ``f``.
        period: Recording period.
        coverage: Share in ``[0, 1]``, or ``None`` when unknown.
    """

    facility: FacilityId
    period: Period
    coverage: float | None

    def __post_init__(self) -> None:
        """Validate the coverage bounds."""
        if self.coverage is not None and (
            not math.isfinite(self.coverage) or not 0.0 <= self.coverage <= 1.0
        ):
            raise ValueError("coverage must be in [0, 1] or None")

    @property
    def is_known(self) -> bool:
        """Return whether coverage is known (full or a known share), per OQ-8."""
        return self.coverage is not None

    @property
    def is_full(self) -> bool:
        """Return whether every request of the facility in the period was recorded."""
        return self.coverage == 1.0

"""Tickets, operational indicators and facility functional state (Paper 4 §4–5). Interfaces only.

Tickets are anonymous (:class:`~solidaritynode_core.model.Ticket`; OQ-21 open). Observations
are used for learning only from facilities with full or known recording coverage (OQ-8).
The derivation of facility functional state from indicators is **OQ-17 (open)**.

Spec gap to raise: Paper 4 computes indicators and functional state **per facility**, and
recording coverage is per facility, but the ticket fields of Paper 4 §4.1 (and the privacy
rules in AGENTS.md) carry no facility. How tickets are attributed to facilities is not
specified; the interfaces below take the attribution as an explicit input.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol

from solidaritynode_core.model import (
    FacilityFunctionalState,
    FacilityId,
    IndexedValues,
    Period,
    RecordingCoverage,
    Service,
    Ticket,
)

__all__ = ["FacilityStateClassifier", "OperationalIndicatorCalculator", "TicketSource"]


class TicketSource(Protocol):
    """Read anonymous tickets for a period (Paper 4 §4.1)."""

    def tickets(self, period: Period) -> Iterable[Ticket]:
        """Yield tickets whose request time falls in ``period``."""
        ...

    def coverage(self, period: Period) -> Sequence[RecordingCoverage]:
        """Return recording coverage per facility for ``period`` (OQ-8)."""
        ...


class OperationalIndicatorCalculator(Protocol):
    """Operational indicators (Paper 4 §4.2).

    Demand rate, waiting time, fulfilment delay, appointment adherence, overdue requests,
    expired requests, service coverage, unfulfilled need. A request not fulfilled within the
    service's maximum acceptable waiting time is unmet (OQ-26).
    """

    def indicators(
        self,
        tickets: Mapping[FacilityId, Sequence[Ticket]],
        services: Sequence[Service],
        period: Period,
    ) -> IndexedValues:
        """Return indicators, dims ``(facility, service, time)`` plus an indicator axis.

        Args:
            tickets: Tickets attributed to facilities (attribution rule: see module note).
            services: Service definitions (units, maximum acceptable waiting time).
            period: Period of analysis (reference period: OQ-25).
        """
        ...


class FacilityStateClassifier(Protocol):
    """Facility functional state from operational indicators (Paper 4 §5; **OQ-17 open**)."""

    def classify(
        self, indicators: IndexedValues
    ) -> Mapping[FacilityId, Mapping[FacilityFunctionalState, float]]:
        """Return a probability over functional states per facility."""
        ...

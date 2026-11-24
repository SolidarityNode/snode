"""Anonymous service-request (ticket) router (placeholder, no endpoints, nothing persisted).

The request and response schemas live in :mod:`solidaritynode_backend.schemas.tickets` and
mirror ``solidaritynode_core.model.Ticket`` (Paper 4 §4.1).

**OQ-21 (open): re-identification risk.** Tickets are anonymous, but spatial unit, group,
facility (OQ-29) and timestamps together can identify people in small units. Minimum cell
sizes (k-anonymity), retention and aggregation rules must be decided (ADR 0010) **before** any
endpoint stores or returns ticket data. The "first request in this period" flag must never
become an identifier.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/requests", tags=["requests"])

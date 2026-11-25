"""Anonymous service-request (ticket) router: municipal installations only (ADR 0012).

Not mounted when ``DEPLOYMENT_MODE=hub``: tickets never exist in the hub, so every
``/requests`` path answers 404 there. Nothing is persisted yet; the only endpoint reports that.

The request and response schemas live in :mod:`solidaritynode_backend.schemas.tickets` and
mirror ``solidaritynode_core.model.Ticket`` (Paper 4 §4.1).

**OQ-21 (open): re-identification risk.** Tickets are anonymous, but spatial unit, group,
facility (OQ-29) and timestamps together can identify people in small units. Minimum cell
sizes (k-anonymity), retention and aggregation rules must be decided (ADR 0010) **before** any
endpoint stores or returns ticket data. The "first request in this period" flag must never
become an identifier.
"""

from fastapi import APIRouter

from solidaritynode_backend.auth import CurrentUser
from solidaritynode_backend.schemas.api import RoleFeatureOut

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get("/status", response_model=RoleFeatureOut)
def requests_status(user: CurrentUser) -> RoleFeatureOut:
    """Whether tickets are stored: not yet, until OQ-21 rules are decided (ADR 0010)."""
    return RoleFeatureOut(
        role="municipality",
        feature="tickets",
        implemented=False,
        note="No ticket is stored until the OQ-21 rules are decided (ADR 0010).",
    )
